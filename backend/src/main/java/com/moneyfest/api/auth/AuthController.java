package com.moneyfest.api.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/auth")
class AuthController {
    record Credentials(@NotBlank @Email @Size(max=254) String email,
                       @NotBlank @Size(min=10,max=72) String password,
                       @Size(max=80) String displayName) {}
    private final JdbcClient db;
    private final PasswordEncoder encoder;
    private final HttpSessionSecurityContextRepository contexts;
    private final Map<String, Attempt> attempts = new ConcurrentHashMap<>();
    private record Attempt(int count, Instant expires) {}
    AuthController(JdbcClient db, PasswordEncoder encoder, HttpSessionSecurityContextRepository contexts) {
        this.db=db; this.encoder=encoder; this.contexts=contexts;
    }
    @GetMapping("/csrf") Map<String,String> csrf(CsrfToken token) {
        return Map.of("token", token.getToken(), "headerName", token.getHeaderName());
    }
    @GetMapping("/me") Map<String,Object> me(java.security.Principal principal) {
        return publicUser(principal.getName());
    }
    private Map<String,Object> publicUser(String email) {
        return db.sql("SELECT id,email,display_name FROM app_user WHERE email=:email").param("email",email).query().singleRow();
    }
    private String normalized(Credentials input) {
        if (input.password().getBytes(StandardCharsets.UTF_8).length > 72)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Password must be at most 72 UTF-8 bytes.");
        return input.email().trim().toLowerCase(Locale.ROOT);
    }
    private void throttle(HttpServletRequest request) {
        Instant now=Instant.now();
        // Local instance limit; a shared limiter is required before horizontal scaling.
        attempts.entrySet().removeIf(e -> e.getValue().expires().isBefore(now));
        var attempt=attempts.compute(request.getRemoteAddr(), (k,v) ->
            v==null ? new Attempt(1,now.plusSeconds(60)) : new Attempt(v.count()+1,v.expires()));
        if(attempt.count()>20) throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,"Too many attempts. Try again in a minute.");
    }
    @PostMapping("/register") @ResponseStatus(HttpStatus.CREATED) @Transactional
    Map<String,Object> register(@Valid @RequestBody Credentials input, HttpServletRequest request, HttpServletResponse response) {
        throttle(request);
        String email=normalized(input);
        String name=input.displayName()==null ? email.split("@")[0] : input.displayName().trim();
        if(name.isBlank()) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Enter your name.");
        var inserted=db.sql("INSERT INTO app_user(email,password_hash,display_name) VALUES(:email,:hash,:name) ON CONFLICT(email) DO NOTHING RETURNING id")
            .param("email",email).param("hash",encoder.encode(input.password())).param("name",name).query(Long.class).optional();
        if(inserted.isEmpty()) throw new ResponseStatusException(HttpStatus.CONFLICT,"An account with this email already exists.");
        db.sql("INSERT INTO user_preferences(user_id) VALUES(:id)").param("id",inserted.get()).update();
        authenticate(email,request,response);
        return publicUser(email);
    }
    @PostMapping("/login") Map<String,Object> login(@Valid @RequestBody Credentials input, HttpServletRequest request, HttpServletResponse response) {
        throttle(request);
        String email=normalized(input);
        var hash=db.sql("SELECT password_hash FROM app_user WHERE email=:email").param("email",email).query(String.class).optional();
        // Perform a hash check even when the email is unknown.
        String candidate=hash.orElse("$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy");
        if(!encoder.matches(input.password(),candidate) || hash.isEmpty())
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,"Email or password is incorrect.");
        authenticate(email,request,response);
        return publicUser(email);
    }
    private void authenticate(String email,HttpServletRequest request,HttpServletResponse response) {
        request.getSession(); request.changeSessionId();
        var context=SecurityContextHolder.createEmptyContext();
        context.setAuthentication(UsernamePasswordAuthenticationToken.authenticated(email,null,List.of(new SimpleGrantedAuthority("ROLE_USER"))));
        SecurityContextHolder.setContext(context);
        contexts.saveContext(context,request,response);
        new HttpSessionCsrfTokenRepository().saveToken(null,request,response);
    }
}
