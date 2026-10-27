package com.moneyfest.api.research;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.moneyfest.service.market.MarketService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.security.Principal;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController @RequestMapping("/api/v1/me/portfolio-plan")
class PortfolioPlanController {
    private final JdbcClient db; private final ObjectMapper json; private final MarketService market;
    PortfolioPlanController(JdbcClient db,ObjectMapper json,MarketService market) { this.db=db;this.json=json;this.market=market; }
    private long owner(Principal p) { return db.sql("SELECT id FROM app_user WHERE email=:email").param("email",p.getName()).query(Long.class).single(); }
    record Allocation(@NotNull Long stock_id,@NotNull @DecimalMin("0.01") @DecimalMax("100") BigDecimal weight) {}
    record Plan(@NotNull @Pattern(regexp="INR|USD") String currency,@NotNull @Pattern(regexp="CAUTIOUS|BALANCED|GROWTH") String risk,
        @Min(1) @Max(40) int horizon_years,@NotNull @DecimalMin("1") @Digits(integer=14,fraction=2) BigDecimal budget,
        @NotNull @Size(max=30) List<@Valid Allocation> allocations) {}
    @GetMapping Map<String,Object> get(Principal p) {
        var plan=db.sql("SELECT currency,risk,horizon_years,budget,allocations::text AS allocations_json,updated_at FROM portfolio_plan WHERE user_id=:uid").param("uid",owner(p)).query().listOfRows();
        if(plan.isEmpty()) return Map.of("saved",false);
        var result=new LinkedHashMap<>(plan.getFirst()); result.put("saved",true);
        result.put("stocks",db.sql("""
            SELECT s.id AS stock_id,s.ticker,s.symbol,s.name,s.exchange,s.currency,s.sector,
                (a->>'weight')::numeric AS weight,b.close,b.date
            FROM portfolio_plan p CROSS JOIN LATERAL jsonb_array_elements(p.allocations) a
            JOIN stock s ON s.id=(a->>'stock_id')::bigint
            LEFT JOIN LATERAL (SELECT close,date FROM price_bar WHERE stock_id=s.id ORDER BY date DESC LIMIT 1) b ON true
            WHERE p.user_id=:uid ORDER BY s.ticker
            """).param("uid",owner(p)).query().listOfRows());
        return result;
    }
    record ReviewQuestion(@NotBlank @Size(min=3,max=400) String question) {}
    @PostMapping("/review") Map<String,Object> review(Principal p,@Valid @RequestBody ReviewQuestion question) {
        var plan=get(p);
        if(!Boolean.TRUE.equals(plan.get("saved"))) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Save a portfolio draft first.");
        @SuppressWarnings("unchecked") var stocks=(List<Map<String,Object>>)plan.get("stocks");
        BigDecimal total=BigDecimal.ZERO,largest=BigDecimal.ZERO; String largestName="";
        for(var stock:stocks) {
            var weight=(BigDecimal)stock.get("weight");total=total.add(weight);
            if(weight.compareTo(largest)>0) { largest=weight;largestName=stock.get("symbol").toString(); }
        }
        String q=question.question().toLowerCase(Locale.ROOT);
        StringBuilder answer=new StringBuilder("Rules-based review of your saved draft: ");
        answer.append(stocks.size()).append(" stocks in ").append(plan.get("currency")).append(", ").append(total.stripTrailingZeros().toPlainString()).append("% allocated. ");
        if(stocks.isEmpty()) answer.append("Search and add stocks before comparing an allocation. ");
        else answer.append("Largest position: ").append(largestName).append(" at ").append(largest.stripTrailingZeros().toPlainString()).append("%. ")
            .append(largest.compareTo(BigDecimal.valueOf(25))>0?"One company exceeds the 25% concentration check. Compare a lower single-stock limit and businesses with different drivers. ":"No position exceeds the 25% check, but common sector and business exposures can still concentrate risk. ");
        if(q.matches("(?s).*\\b(news|headline|catalyst|event)\\b.*")) answer.append("Open each selected stock's research page to inspect dated headlines and source links. Headlines alone cannot prove a cause or forecast returns. ");
        else if(q.matches("(?s).*\\b(best|optimal|return|pick|recommend)\\b.*")) answer.append("This rules-based coach cannot rank securities or determine a best portfolio. Compare your goal, cash needs, acceptable losses and diversification before choosing stocks. ");
        else if(q.matches("(?s).*\\b(equal|weight|rebalance)\\b.*")) answer.append("Equal weights can reduce single-name imbalance, but do not ensure sector diversification. The Equal weights control lets you compare that scenario without changing your actual holdings. ");
        if(plan.get("risk").equals("CAUTIOUS")) answer.append("A cautious preference does not make a stock-only portfolio low risk; compare cash and other asset classes. ");
        if(((Number)plan.get("horizon_years")).intValue()<5) answer.append("Your horizon is under five years; assess whether you can avoid selling during a downturn. ");
        if(plan.get("currency").equals("USD")) answer.append("For INR-based goals, include USD/INR changes, remittance costs and applicable taxes. ");
        answer.append("This is an allocation checklist, not a security ranking or buy/sell recommendation. Connect Gemini for a broader conversational review.");
        return Map.of("answer",answer.toString(),"model","allocation-rules-v1","sources",List.of(),"as_of",java.time.Instant.now().toString());
    }
    @PutMapping @Transactional Map<String,Object> save(Principal p,@Valid @RequestBody Plan plan) throws Exception {
        BigDecimal total=BigDecimal.ZERO; Set<Long> ids=new HashSet<>();
        for(var a:plan.allocations()) {
            if(!ids.add(a.stock_id())) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Each stock can appear only once.");
            if(db.sql("SELECT count(*) FROM stock WHERE id=:id AND currency=:currency").param("id",a.stock_id()).param("currency",plan.currency()).query(Long.class).single()!=1)
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Choose stocks in the plan currency.");
            total=total.add(a.weight());
        }
        if(total.compareTo(BigDecimal.valueOf(100))>0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Allocation cannot exceed 100%.");
        db.sql("""
            INSERT INTO portfolio_plan(user_id,currency,risk,horizon_years,budget,allocations) VALUES(:uid,:currency,:risk,:years,:budget,CAST(:items AS jsonb))
            ON CONFLICT(user_id) DO UPDATE SET currency=excluded.currency,risk=excluded.risk,horizon_years=excluded.horizon_years,
                budget=excluded.budget,allocations=excluded.allocations,updated_at=now()
            """).param("uid",owner(p)).param("currency",plan.currency()).param("risk",plan.risk()).param("years",plan.horizon_years()).param("budget",plan.budget()).param("items",json.writeValueAsString(plan.allocations())).update();
        ids.forEach(market::enqueue);
        return get(p);
    }
}
