package com.moneyfest.api.market;

import com.moneyfest.service.market.MarketService;

import java.security.Principal;
import java.util.*;
import jakarta.validation.constraints.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController @Validated @RequestMapping("/api/v1")
class NewsController {
    private final JdbcClient db;
    private final MarketService market;
    NewsController(JdbcClient db,MarketService market) { this.db=db; this.market=market; }
    private long owner(Principal p) { return db.sql("SELECT id FROM app_user WHERE email=:email").param("email",p.getName()).query(Long.class).single(); }
    @GetMapping("/market/status") Map<String,Object> status() {
        return Map.of("enabled",market.enabled(),"refreshing",market.busy(),"catalog_count",db.sql("SELECT count(*) FROM stock").query(Long.class).single(),
            "catalog",db.sql("SELECT * FROM market_sync WHERE scope LIKE 'catalog:%' ORDER BY scope").query().listOfRows());
    }
    @PostMapping("/me/refresh") Map<String,Object> refresh(Principal p) {
        var ids=db.sql("SELECT stock_id FROM position WHERE user_id=:uid UNION SELECT stock_id FROM watchlist_item WHERE user_id=:uid").param("uid",owner(p)).query(Long.class).list();
        int queued=0; for(long id:ids) if(market.enqueue(id)) queued++;
        return Map.of("queued",queued,"enabled",market.enabled());
    }
    @PostMapping("/stocks/{id}/refresh") Map<String,Object> refreshStock(@PathVariable long id) {
        if(db.sql("SELECT count(*) FROM stock WHERE id=:id").param("id",id).query(Long.class).single()==0)
            throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.NOT_FOUND,"Stock not found");
        return Map.of("queued",market.enqueue(id),"enabled",market.enabled());
    }
    @GetMapping("/me/news") Map<String,Object> news(Principal p,
        @RequestParam(defaultValue="all") @Pattern(regexp="all|held|watched") String scope,
        @RequestParam(defaultValue="ALL") @Pattern(regexp="ALL|POSITIVE|NEGATIVE|MIXED|NEUTRAL") String sentiment,
        @RequestParam(required=false) Long stockId,
        @RequestParam(defaultValue="false") boolean unread,
        @RequestParam(defaultValue="0") @Min(0) @Max(100000) int offset) {
        long uid=owner(p);
        String from="""
            FROM news_item n JOIN stock s ON s.id=n.stock_id
            LEFT JOIN news_read r ON r.news_id=n.id AND r.user_id=:uid
            WHERE (:stock IS NULL OR n.stock_id=:stock)
            AND (:stock IS NOT NULL OR
                (:scope IN ('all','held') AND EXISTS(SELECT 1 FROM position p WHERE p.user_id=:uid AND p.stock_id=s.id)) OR
                (:scope IN ('all','watched') AND EXISTS(SELECT 1 FROM watchlist_item w WHERE w.user_id=:uid AND w.stock_id=s.id)))
            AND (:sentiment='ALL' OR n.sentiment=:sentiment) AND (NOT :unread OR r.news_id IS NULL)
            AND n.published_at>now()-interval '7 days'
            """;
        // Explicit BIGINT avoids PostgreSQL's untyped-null parameter ambiguity.
        from=from.replace(":stock IS", "CAST(:stock AS bigint) IS");
        var items=db.sql("SELECT n.*,s.ticker,s.name,s.exchange,(r.news_id IS NOT NULL) AS read "+from+" ORDER BY n.published_at DESC,n.id DESC LIMIT 30 OFFSET :offset")
            .param("uid",uid).param("stock",stockId).param("scope",scope).param("sentiment",sentiment).param("unread",unread).param("offset",offset).query().listOfRows();
        long total=db.sql("SELECT count(*) "+from).param("uid",uid).param("stock",stockId).param("scope",scope).param("sentiment",sentiment).param("unread",unread).query(Long.class).single();
        var sync=db.sql("""
            SELECT m.*,s.ticker FROM market_sync m JOIN stock s ON m.scope='news:'||s.id OR m.scope='prices:'||s.id
            WHERE (CAST(:stock AS bigint) IS NOT NULL AND s.id=:stock) OR
            (CAST(:stock AS bigint) IS NULL AND (EXISTS(SELECT 1 FROM position WHERE user_id=:uid AND stock_id=s.id)
            OR EXISTS(SELECT 1 FROM watchlist_item WHERE user_id=:uid AND stock_id=s.id))) ORDER BY s.ticker,m.scope
            """).param("stock",stockId).param("uid",uid).query().listOfRows();
        return Map.of("items",items,"total",total,"sync",sync,"refreshing",market.busy());
    }
    @GetMapping("/market/news") Map<String,Object> marketNews(@RequestParam(defaultValue="US") @Pattern(regexp="US|IN") String market) {
        var rows=db.sql("SELECT n.*,s.ticker,s.symbol,s.name,s.exchange,false AS read FROM news_item n JOIN stock s ON s.id=n.stock_id WHERE s.currency=:currency AND n.published_at>now()-interval '7 days' ORDER BY n.published_at DESC LIMIT 30")
            .param("currency",market.equals("US")?"USD":"INR").query().listOfRows();
        return Map.of("items",rows,"refreshing",this.market.busy());
    }
    @PutMapping("/me/news/{id}/read") Map<String,Boolean> read(Principal p,@PathVariable long id) {
        int updated=db.sql("""
            INSERT INTO news_read(user_id,news_id) SELECT :uid,n.id FROM news_item n WHERE n.id=:id
            AND (EXISTS(SELECT 1 FROM position WHERE user_id=:uid AND stock_id=n.stock_id)
              OR EXISTS(SELECT 1 FROM watchlist_item WHERE user_id=:uid AND stock_id=n.stock_id))
            ON CONFLICT DO NOTHING
            """).param("uid",owner(p)).param("id",id).update();
        return Map.of("ok",updated>0);
    }
}
