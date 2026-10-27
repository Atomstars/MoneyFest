package com.moneyfest.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
class SecurityConfig {
    @Bean PasswordEncoder passwords() { return new BCryptPasswordEncoder(); }
    @Bean HttpSessionSecurityContextRepository contexts() { return new HttpSessionSecurityContextRepository(); }
    @Bean SecurityFilterChain security(HttpSecurity http, HttpSessionSecurityContextRepository contexts) throws Exception {
        return http
            .securityContext(c -> c.securityContextRepository(contexts))
            .authorizeHttpRequests(a -> a
                .requestMatchers("/api/v1/health", "/api/v1/auth/csrf", "/api/v1/auth/register", "/api/v1/auth/login", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(e -> e
                .authenticationEntryPoint((q,r,x) -> { r.setStatus(401); r.setContentType("application/json"); r.getWriter().write("{\"detail\":\"Please sign in to continue.\"}"); })
                .accessDeniedHandler((q,r,x) -> { r.setStatus(403); r.setContentType("application/json"); r.getWriter().write("{\"detail\":\"Request verification failed. Refresh and try again.\"}"); }))
            .logout(l -> l.logoutUrl("/api/v1/auth/logout").logoutSuccessHandler((q,r,a) -> { r.setContentType("application/json"); r.getWriter().write("{\"ok\":true}"); }))
            .build();
    }
}
