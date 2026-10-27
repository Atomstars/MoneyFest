package com.moneyfest.api.portfolio;

import com.moneyfest.service.market.MarketService;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.*;
import java.security.Principal;
import java.time.LocalDate;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController @Validated @RequestMapping("/api/v1")
class PortfolioController {
    private final JdbcClient db;
    private final MarketService market;
    PortfolioController(JdbcClient db,MarketService market) { this.db=db; this.market=market; }
    private long owner(Principal p) {
        return db.sql("SELECT id FROM app_user WHERE email=:email").param("email",p.getName()).query(Long.class).single();
    }
    private long stock(String ticker) {
        return db.sql("SELECT id FROM stock WHERE ticker=:ticker").param("ticker",ticker.toUpperCase(Locale.ROOT))
            .query(Long.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Stock is not in the supported catalog."));
    }
    private void exists(long id) {
        if(db.sql("SELECT count(*) FROM stock WHERE id=:id").param("id",id).query(Long.class).single()==0)
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Stock not found.");
    }
    @GetMapping("/health") Map<String,Object> health() {
        db.sql("SELECT 1").query(Integer.class).single();
        return Map.of("status","ok","backend","java","market_data",market.enabled()?"best_effort":"disabled");
    }
    @GetMapping("/stocks") List<Map<String,Object>> stocks(Principal p,@RequestParam(defaultValue="") @Size(max=100) String query,
        @RequestParam(defaultValue="all") @Pattern(regexp="all|held|watched") String filter,
        @RequestParam(defaultValue="ALL") @Pattern(regexp="ALL|NSE|BSE|NASDAQ|NYSE|AMEX|ARCA|BATS|IEX") String exchange,
        @RequestParam(defaultValue="ALL") @Pattern(regexp="ALL|IN|US") String market,
        @RequestParam(defaultValue="0") @Min(0) @Max(100000) int offset) {
        return db.sql("""
            SELECT s.id AS stock_id,s.ticker,s.name,s.sector,s.exchange,s.symbol,s.isin,s.currency,
              EXISTS(SELECT 1 FROM position WHERE user_id=:uid AND stock_id=s.id) AS held,
              EXISTS(SELECT 1 FROM watchlist_item WHERE user_id=:uid AND stock_id=s.id) AS watched,
              b.date,b.close,
              CASE WHEN prev.close IS NOT NULL THEN (b.close/prev.close-1) END AS change_pct,
              a.outcome AS gate_result
            FROM stock s
            LEFT JOIN LATERAL (SELECT date,close FROM price_bar WHERE stock_id=s.id ORDER BY date DESC LIMIT 1) b ON true
            LEFT JOIN LATERAL (SELECT close FROM price_bar WHERE stock_id=s.id AND date<b.date ORDER BY date DESC LIMIT 1) prev ON true
            LEFT JOIN assessment a ON a.stock_id=s.id AND a.date=b.date
            WHERE lower(s.ticker||' '||s.name||' '||coalesce(s.sector,'')) LIKE :query
            AND (:exchange='ALL' OR s.exchange=:exchange) AND (:market='ALL' OR s.currency=CASE WHEN :market='US' THEN 'USD' ELSE 'INR' END)
            AND (:filter='all' OR (:filter='held' AND EXISTS(SELECT 1 FROM position WHERE user_id=:uid AND stock_id=s.id))
              OR (:filter='watched' AND EXISTS(SELECT 1 FROM watchlist_item WHERE user_id=:uid AND stock_id=s.id)))
            ORDER BY held DESC,watched DESC,s.ticker LIMIT 41 OFFSET :offset
            """).param("uid",owner(p)).param("query","%"+query.trim().toLowerCase(Locale.ROOT).replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%")
            .param("filter",filter).param("market",market).param("exchange",exchange).param("offset",offset).query().listOfRows();
    }
    @GetMapping("/stocks/{id}/prices") List<Map<String,Object>> prices(@PathVariable long id,@RequestParam(defaultValue="90") @Min(1) @Max(730) int days) {
        exists(id);
        return db.sql("""
            SELECT b.date,b.close,(b.close/lag(b.close) OVER(ORDER BY b.date)-1) AS ret,a.outcome AS gate_result
            FROM price_bar b LEFT JOIN assessment a ON a.stock_id=b.stock_id AND a.date=b.date
            WHERE b.stock_id=:id AND b.date>=:start ORDER BY b.date
            """).param("id",id).param("start",LocalDate.now(java.time.ZoneId.of("Asia/Kolkata")).minusDays(days)).query().listOfRows();
    }
    @GetMapping("/stocks/{id}/assessment") Map<String,Object> assessment(@PathVariable long id,@RequestParam(required=false) LocalDate date) {
        exists(id);
        var result=db.sql("SELECT date,outcome,rendered_text,drivers::text AS drivers_json,evidence::text AS evidence_json FROM assessment WHERE stock_id=:id AND (CAST(:date AS date) IS NULL OR date=CAST(:date AS date)) ORDER BY date DESC LIMIT 1")
            .param("id",id).param("date",date==null?null:date.toString()).query().listOfRows();
        return result.isEmpty() ? Map.of("outcome","NOT_ASSESSED","rendered_text","No assessment is available yet. Related headlines are shown separately; a cause for the price move has not been verified.") : result.getFirst();
    }
    record Holding(@NotBlank @Size(max=30) String ticker,
        @NotNull @DecimalMin(value="0",inclusive=false) @Digits(integer=14,fraction=6) BigDecimal qty,
        @NotNull @DecimalMin("0") @Digits(integer=14,fraction=6) BigDecimal avg_cost) {}
    @PutMapping("/me/portfolio/positions") @Transactional Map<String,Object> put(Principal p,@Valid @RequestBody Holding in) {
        long id=stock(in.ticker());
        db.sql("INSERT INTO position(user_id,stock_id,qty,avg_cost) VALUES(:uid,:id,:qty,:cost) ON CONFLICT(user_id,stock_id) DO UPDATE SET qty=excluded.qty,avg_cost=excluded.avg_cost,updated_at=now()")
            .param("uid",owner(p)).param("id",id).param("qty",in.qty()).param("cost",in.avg_cost()).update();
        market.enqueue(id);
        return Map.of("holding_id",id);
    }
    @DeleteMapping("/me/portfolio/positions/{ticker}") Map<String,String> delete(Principal p,@PathVariable String ticker) {
        db.sql("DELETE FROM position WHERE user_id=:uid AND stock_id=:id").param("uid",owner(p)).param("id",stock(ticker)).update();
        return Map.of("removed",ticker);
    }
    // DTO rates are fractions: 0.1 means 10%, matching the existing browser contract.
    private BigDecimal percent(BigDecimal n,BigDecimal d) { return d.signum()==0 ? null : n.divide(d,8,RoundingMode.HALF_UP); }
    private BigDecimal number(Map<String,Object> row,String key) { return (BigDecimal)row.get(key); }
    private LocalDate latestDate(String currency) { return db.sql("SELECT max(b.date) FROM price_bar b JOIN stock s ON s.id=b.stock_id WHERE s.currency=:currency").param("currency",currency).query(LocalDate.class).optional().orElse(null); }
    private List<Map<String,Object>> positions(long uid,LocalDate date,String currency) {
        var rows=db.sql("""
            SELECT s.id AS stock_id,s.ticker,s.name,s.sector,s.currency,s.exchange,p.qty,p.avg_cost,b.close AS price,
              prev.close AS prev_close,a.outcome AS gate_result,a.outcome,
              p.qty*p.avg_cost AS invested,p.qty*b.close AS market_value
            FROM position p JOIN stock s ON s.id=p.stock_id
            LEFT JOIN price_bar b ON b.stock_id=s.id AND b.date=:date
            LEFT JOIN LATERAL (SELECT close FROM price_bar WHERE stock_id=s.id AND date<:date ORDER BY date DESC LIMIT 1) prev ON true
            LEFT JOIN assessment a ON a.stock_id=s.id AND a.date=:date
            WHERE p.user_id=:uid AND s.currency=:currency ORDER BY s.ticker
            """).param("uid",uid).param("date",date).param("currency",currency).query().listOfRows();
        List<Map<String,Object>> result=new ArrayList<>();
        for(var r:rows) {
            var row=new LinkedHashMap<>(r);
            BigDecimal value=number(row,"market_value"),invested=number(row,"invested"),price=number(row,"price"),prev=number(row,"prev_close");
            row.put("pnl",value==null?null:value.subtract(invested));
            row.put("pnl_pct",value==null?null:percent(value.subtract(invested),invested));
            row.put("day_change",price==null||prev==null?null:price.subtract(prev).multiply(number(row,"qty")));
            row.put("day_change_pct",price==null||prev==null?null:percent(price.subtract(prev),prev));
            result.add(row);
        }
        return result;
    }
    @GetMapping("/me/portfolio") Map<String,Object> portfolio(Principal p,@RequestParam(defaultValue="INR") @Pattern(regexp="INR|USD") String currency) {
        LocalDate date=latestDate(currency);
        var rows=positions(owner(p),date,currency);
        BigDecimal invested=BigDecimal.ZERO,value=BigDecimal.ZERO,pricedInvested=BigDecimal.ZERO,day=BigDecimal.ZERO,previousValue=BigDecimal.ZERO;
        int priced=0,dayPriced=0;
        for(var r:rows) {
            invested=invested.add(number(r,"invested"));
            if(r.get("market_value")!=null) {
                priced++; value=value.add(number(r,"market_value")); pricedInvested=pricedInvested.add(number(r,"invested"));
                if(r.get("day_change")!=null) { dayPriced++; day=day.add(number(r,"day_change")); previousValue=previousValue.add(number(r,"prev_close").multiply(number(r,"qty"))); }
            }
        }
        for(var r:rows) r.put("weight",r.get("market_value")==null?null:percent(number(r,"market_value"),value));
        Map<String,Object> result=new LinkedHashMap<>();
        result.put("currency",currency); result.put("as_of",date); result.put("positions",rows); result.put("total_invested",invested);
        boolean empty=rows.isEmpty();
        result.put("total_value",priced==0&&!empty?null:value);
        result.put("total_pnl",priced==0&&!empty?null:value.subtract(pricedInvested));
        result.put("total_pnl_pct",percent(value.subtract(pricedInvested),pricedInvested));
        result.put("day_change",dayPriced==0&&!empty?null:day);
        result.put("day_change_pct",percent(day,previousValue));
        result.put("priced_positions",priced); result.put("unpriced_positions",rows.size()-priced);
        result.put("day_unpriced_positions",priced-dayPriced);
        return result;
    }
    @GetMapping("/me/portfolio/allocation") List<Map<String,Object>> allocation(Principal p,@RequestParam(defaultValue="INR") @Pattern(regexp="INR|USD") String currency) {
        var rows=positions(owner(p),latestDate(currency),currency);
        Map<String,BigDecimal> sectors=new TreeMap<>();
        for(var r:rows) if(r.get("market_value")!=null) sectors.merge(Objects.toString(r.get("sector"),"Unclassified"),number(r,"market_value"),BigDecimal::add);
        BigDecimal total=sectors.values().stream().reduce(BigDecimal.ZERO,BigDecimal::add);
        return sectors.entrySet().stream().map(e -> { Map<String,Object> r=new LinkedHashMap<>(); r.put("sector",e.getKey()); r.put("value",e.getValue()); r.put("weight",percent(e.getValue(),total)); return r; }).toList();
    }
    @GetMapping("/me/portfolio/history") List<Map<String,Object>> history(Principal p,@RequestParam(defaultValue="INR") @Pattern(regexp="INR|USD") String currency,@RequestParam(defaultValue="90") @Min(1) @Max(730) int days) {
        return db.sql("""
            SELECT b.date,sum(p.qty*b.close) AS value FROM position p JOIN stock s ON s.id=p.stock_id JOIN price_bar b ON b.stock_id=p.stock_id
            WHERE p.user_id=:uid AND s.currency=:currency AND b.date>=:start GROUP BY b.date
            HAVING count(*)=(SELECT count(*) FROM position p2 JOIN stock s2 ON s2.id=p2.stock_id WHERE p2.user_id=:uid AND s2.currency=:currency) ORDER BY b.date
            """).param("currency",currency).param("uid",owner(p)).param("start",LocalDate.now(java.time.ZoneId.of("Asia/Kolkata")).minusDays(days)).query().listOfRows();
    }
    @GetMapping("/me/watchlist") List<Map<String,Object>> watchlist(Principal p) {
        return db.sql("SELECT s.id AS stock_id,s.ticker,s.name FROM stock s JOIN watchlist_item w ON w.stock_id=s.id WHERE w.user_id=:uid ORDER BY s.ticker").param("uid",owner(p)).query().listOfRows();
    }
    @PutMapping("/me/watchlist/{id}") Map<String,Boolean> watch(Principal p,@PathVariable long id) {
        exists(id); db.sql("INSERT INTO watchlist_item(user_id,stock_id) VALUES(:uid,:id) ON CONFLICT DO NOTHING").param("uid",owner(p)).param("id",id).update(); market.enqueue(id); return Map.of("ok",true);
    }
    @DeleteMapping("/me/watchlist/{id}") Map<String,Boolean> unwatch(Principal p,@PathVariable long id) {
        db.sql("DELETE FROM watchlist_item WHERE user_id=:uid AND stock_id=:id").param("uid",owner(p)).param("id",id).update(); return Map.of("ok",true);
    }
    record Preferences(@NotNull @Pattern(regexp="ALL|EXPLAINED_ONLY|HIGH_ONLY") String alert_level,@NotNull Boolean quiet_market,@NotNull Boolean daily_digest) {}
    @GetMapping("/me/preferences") Map<String,Object> prefs(Principal p) {
        return db.sql("SELECT alert_level,quiet_market,daily_digest FROM user_preferences WHERE user_id=:uid").param("uid",owner(p)).query().singleRow();
    }
    @PutMapping("/me/preferences") Map<String,Object> prefs(Principal p,@Valid @RequestBody Preferences in) {
        db.sql("UPDATE user_preferences SET alert_level=:level,quiet_market=:quiet,daily_digest=:digest WHERE user_id=:uid")
            .param("uid",owner(p)).param("level",in.alert_level()).param("quiet",in.quiet_market()).param("digest",in.daily_digest()).update(); return prefs(p);
    }
}
