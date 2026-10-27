package com.moneyfest.service.fund;

import com.moneyfest.provider.MarketProvider;

import java.io.*;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/** AMFI publishes end-of-day NAV; these are not intraday fund prices. */
@Service
public class FundService {
    public record Scheme(String code,String isin,String name,String plan,String option,String category,String amc,BigDecimal nav,LocalDate date) {}
    private static final DateTimeFormatter AMFI_DATE=DateTimeFormatter.ofPattern("dd-MMM-uuuu",Locale.ENGLISH);
    private final JdbcClient db;
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final boolean enabled;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).build();
    FundService(JdbcClient db,JdbcTemplate jdbc,TransactionTemplate tx,@Value("${moneyfest.market.enabled:true}") boolean enabled) {
        this.db=db;this.jdbc=jdbc;this.tx=tx;this.enabled=enabled;
    }
    @Scheduled(initialDelay=15000,fixedDelay=3600000)
    void sync() {
        if(!enabled) return;
        long fresh=db.sql("SELECT count(*) FROM market_sync WHERE scope='funds:amfi' AND succeeded_at>now()-interval '12 hours'").query(Long.class).single();
        if(fresh>0) return;
        db.sql("INSERT INTO market_sync(scope,status) VALUES('funds:amfi','UPDATING') ON CONFLICT(scope) DO UPDATE SET attempted_at=now(),status='UPDATING',detail=NULL").update();
        try {
            var request=HttpRequest.newBuilder(URI.create("https://portal.amfiindia.com/spages/NAVOpen.txt"))
                .timeout(Duration.ofSeconds(35)).header("User-Agent","Moneyfest/1.0").GET().build();
            var response=http.send(request,HttpResponse.BodyHandlers.ofByteArray());
            if(response.statusCode()!=200 || response.body().length>15_000_000) throw new IOException("AMFI response unavailable or too large");
            var schemes=parse(new String(response.body(),StandardCharsets.UTF_8));
            if(schemes.size()<1000) throw new IOException("Incomplete AMFI NAV report");
            tx.executeWithoutResult(status->{
                jdbc.batchUpdate("""
                    INSERT INTO fund_scheme(code,isin,name,plan,option_name,category,amc,updated_at)
                    VALUES(?,?,?,?,?,?,?,now()) ON CONFLICT(code) DO UPDATE SET
                    isin=excluded.isin,name=excluded.name,plan=excluded.plan,option_name=excluded.option_name,
                    category=excluded.category,amc=excluded.amc,updated_at=now(),active=true
                    """,schemes,500,(ps,s)->{ps.setString(1,s.code());ps.setString(2,s.isin());ps.setString(3,s.name());ps.setString(4,s.plan());ps.setString(5,s.option());ps.setString(6,s.category());ps.setString(7,s.amc());});
                jdbc.batchUpdate("INSERT INTO fund_nav(code,date,nav) VALUES(?,?,?) ON CONFLICT(code,date) DO UPDATE SET nav=excluded.nav",schemes,500,
                    (ps,s)->{ps.setString(1,s.code());ps.setObject(2,s.date());ps.setBigDecimal(3,s.nav());});
            });
            db.sql("UPDATE market_sync SET status='OK',succeeded_at=now(),detail=:detail WHERE scope='funds:amfi'")
                .param("detail",schemes.size()+" open ended schemes synced").update();
        } catch(Exception e) {
            db.sql("UPDATE market_sync SET status='ERROR',detail='AMFI refresh failed; saved NAV retained' WHERE scope='funds:amfi'").update();
            LoggerFactory.getLogger(getClass()).warn("AMFI NAV sync failed: {}",e.toString());
        }
    }
    public static List<Scheme> parse(String report) {
        List<Scheme> schemes=new ArrayList<>();
        String category="",amc="";
        for(String raw:report.split("\\R")) {
            String line=raw.trim();
            if(line.startsWith("Open Ended Schemes(")) {
                category=line.substring("Open Ended Schemes(".length()).replaceFirst("\\)$","").trim(); amc=""; continue;
            }
            if(line.isEmpty() || line.startsWith("Scheme Code")) continue;
            if(!Character.isDigit(line.charAt(0))) { if(!category.isEmpty()) amc=line; continue; }
            String[] p=line.split(";",-1);
            if(p.length!=8 || category.isEmpty() || amc.isEmpty() || !p[0].trim().matches("\\d{3,10}")) continue;
            try {
                BigDecimal nav=new BigDecimal(p[6].trim());
                LocalDate date=LocalDate.parse(p[7].trim(),AMFI_DATE);
                if(nav.signum()<=0 || date.isAfter(LocalDate.now(MarketProvider.INDIA).plusDays(1))) continue;
                String name=p[3].trim(),plan=p[4].trim(),option=p[5].trim(),isin=p[1].trim();
                if(name.isBlank() || name.length()>240 || category.length()>180 || amc.length()>160) continue;
                schemes.add(new Scheme(p[0].trim(),isin.matches("IN[A-Z0-9]{10}")?isin:null,name,plan,option,category,amc,nav,date));
            } catch(Exception ignored) { /* A few schemes publish a missing NAV. */ }
        }
        return schemes;
    }
}
