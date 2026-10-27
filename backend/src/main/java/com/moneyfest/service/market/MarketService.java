package com.moneyfest.service.market;

import com.moneyfest.provider.MarketProvider;

import jakarta.annotation.PreDestroy;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service @EnableScheduling
public class MarketService {
    private final JdbcClient db;
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final MarketProvider provider;
    private final boolean enabled;
    private final Set<Long> queued=ConcurrentHashMap.newKeySet();
    private final ThreadPoolExecutor worker=new ThreadPoolExecutor(1,1,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(500),r->{var t=new Thread(r,"market-refresh");t.setDaemon(true);return t;});
    MarketService(JdbcClient db,JdbcTemplate jdbc,TransactionTemplate tx,MarketProvider provider,@Value("${moneyfest.market.enabled:true}") boolean enabled) {
        this.db=db; this.jdbc=jdbc; this.tx=tx; this.provider=provider; this.enabled=enabled;
    }
    @PreDestroy void stop() { worker.shutdownNow(); }
    @Scheduled(initialDelay=3000,fixedDelay=900000)
    void scheduledRefresh() {
        if(!enabled) return;
        for(String exchange:List.of("NSE","BSE","US")) {
            String scope="catalog:"+exchange;
            if(db.sql("SELECT count(*) FROM market_sync WHERE scope=:scope AND succeeded_at>:after")
                .param("scope",scope).param("after",java.sql.Timestamp.from(Instant.now().minus(Duration.ofHours(24)))).query(Long.class).single()>0) continue;
            attempt(scope);
            try {
                var instruments=exchange.equals("US")?provider.usCatalog():provider.catalog(exchange);
                tx.executeWithoutResult(status -> jdbc.batchUpdate("""
                    INSERT INTO stock(ticker,symbol,name,exchange,isin,provider_symbol,currency,catalog_at) VALUES(?,?,?,?,?,?,?,now())
                    ON CONFLICT(ticker) DO UPDATE SET symbol=excluded.symbol,exchange=excluded.exchange,
                    isin=excluded.isin,provider_symbol=excluded.provider_symbol,catalog_at=now()
                    """,instruments,500,(ps,s)->{ps.setString(1,s.ticker());ps.setString(2,s.symbol());ps.setString(3,s.name());ps.setString(4,s.exchange());ps.setString(5,s.isin());ps.setString(6,s.providerSymbol());ps.setString(7,exchange.equals("US")?"USD":"INR");}));
                success(scope,instruments.size()+" equities synced");
            } catch(Exception e) { failure(scope,e); }
        }
        var tracked=db.sql("SELECT stock_id FROM position UNION SELECT stock_id FROM watchlist_item").query(Long.class).list();
        for(long id:tracked) enqueue(id);
        for(long id:db.sql("SELECT id FROM stock WHERE ticker IN ('AAPL.US','MSFT.US','NVDA.US','AMZN.US','GOOGL.US','JPM.US')").query(Long.class).list()) enqueue(id);
    }
    public boolean enqueue(long id) {
        if(!enabled || !queued.add(id)) return false;
        try { worker.execute(()->{try { refresh(id); } finally { queued.remove(id); }}); return true; }
        catch(RejectedExecutionException e) { queued.remove(id); return false; }
    }
    public boolean busy() { return !queued.isEmpty(); }
    public boolean enabled() { return enabled; }
    boolean recent(String scope,Duration age) {
        return db.sql("SELECT count(*) FROM market_sync WHERE scope=:scope AND attempted_at>:after")
            .param("scope",scope).param("after",java.sql.Timestamp.from(Instant.now().minus(age))).query(Long.class).single()>0;
    }
    void refresh(long id) {
        var rows=db.sql("SELECT name,symbol,provider_symbol,currency FROM stock WHERE id=:id").param("id",id).query().listOfRows();
        if(rows.isEmpty()) return;
        var stock=rows.getFirst();
        String prices="prices:"+id,news="news:"+id;
        if(!recent(prices,Duration.ofMinutes(15))) {
            attempt(prices);
            try {
                var bars=provider.prices(stock.get("provider_symbol").toString(),stock.get("currency").toString());
                tx.executeWithoutResult(status->jdbc.batchUpdate("INSERT INTO price_bar(stock_id,date,close,source) VALUES(?,?,?,'Yahoo Finance') ON CONFLICT(stock_id,date) DO UPDATE SET close=excluded.close,source=excluded.source",
                    bars,200,(ps,b)->{ps.setLong(1,id);ps.setObject(2,b.date());ps.setBigDecimal(3,b.close());}));
                success(prices,"Closing prices through "+bars.getLast().date());
            } catch(Exception e) { failure(prices,e); }
        }
        if(!recent(news,Duration.ofMinutes(15))) {
            attempt(news);
            try {
                var stories=provider.news(stock.get("name").toString(),stock.get("symbol").toString(),stock.get("currency").toString());
                tx.executeWithoutResult(status->jdbc.batchUpdate("""
                    INSERT INTO news_item(stock_id,headline,summary,url,source,published_at,sentiment,fingerprint)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(stock_id,fingerprint) DO UPDATE SET sentiment=excluded.sentiment
                    """,stories,50,(ps,s)->{ps.setLong(1,id);ps.setString(2,s.headline());ps.setString(3,s.headline());ps.setString(4,s.url());ps.setString(5,s.source());ps.setTimestamp(6,java.sql.Timestamp.from(s.published()));ps.setString(7,s.sentiment());ps.setString(8,s.fingerprint());}));
                success(news,stories.size()+" relevant headlines found");
            } catch(Exception e) { failure(news,e); }
        }
    }
    private void attempt(String scope) { db.sql("INSERT INTO market_sync(scope,status) VALUES(:scope,'UPDATING') ON CONFLICT(scope) DO UPDATE SET attempted_at=now(),status='UPDATING',detail=NULL").param("scope",scope).update(); }
    private void success(String scope,String detail) { db.sql("UPDATE market_sync SET succeeded_at=now(),status='OK',detail=:detail WHERE scope=:scope").param("scope",scope).param("detail",detail).update(); }
    private void failure(String scope,Exception e) {
        String detail=e instanceof java.io.IOException?Objects.toString(e.getMessage(),"Provider unavailable"):"Refresh failed; previously stored data retained";
        db.sql("UPDATE market_sync SET status='ERROR',detail=:detail WHERE scope=:scope").param("scope",scope).param("detail",detail.substring(0,Math.min(250,detail.length()))).update();
        org.slf4j.LoggerFactory.getLogger(getClass()).warn("Market refresh failed for {}: {}",scope,e.toString());
    }
}
