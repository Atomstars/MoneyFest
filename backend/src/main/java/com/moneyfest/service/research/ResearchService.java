package com.moneyfest.service.research;

import com.moneyfest.provider.MarketProvider;

import java.util.*;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
public class ResearchService {
    public record Theme(String id,String label,String query,Set<String> terms) {}
    public static final List<Theme> THEMES=List.of(
        new Theme("BANKING","Banking","India (\"bank stocks\" OR \"bank shares\" OR \"Nifty Bank\" OR \"RBI policy\")",Set.of("bank","banks","RBI","Nifty Bank")),
        new Theme("TECH","Technology","India (\"IT stocks\" OR \"software shares\" OR \"technology stocks\")",Set.of("IT stocks","software","technology","tech")),
        new Theme("ENERGY","Energy","India (\"energy stocks\" OR \"oil prices\" OR \"crude oil\")",Set.of("oil","energy","crude","petroleum")),
        new Theme("PHARMA","Healthcare","India (\"pharma stocks\" OR \"drugmakers\" OR \"healthcare shares\")",Set.of("pharma","healthcare","drugmakers","hospital")),
        new Theme("AUTO","Automobiles","India (\"auto stocks\" OR \"vehicle sales\" OR \"EV shares\")",Set.of("auto","automobile","vehicle","EV")),
        new Theme("MACRO","Global & macro","India stocks (\"global markets\" OR inflation OR tariffs OR \"FII flows\")",Set.of("global","inflation","tariff","rates","markets","FII"))
    );
    private final JdbcClient db; private final JdbcTemplate jdbc; private final MarketProvider provider; private final boolean enabled;
    ResearchService(JdbcClient db,JdbcTemplate jdbc,MarketProvider provider,@Value("${moneyfest.market.enabled:true}") boolean enabled) {
        this.db=db;this.jdbc=jdbc;this.provider=provider;this.enabled=enabled;
    }
    @Scheduled(initialDelay=30000,fixedDelay=3600000)
    void sync() {
        if(!enabled) return;
        for(var theme:THEMES) {
            String scope="research:"+theme.id();
            if(db.sql("SELECT count(*) FROM market_sync WHERE scope=:scope AND succeeded_at>now()-interval '3 hours'").param("scope",scope).query(Long.class).single()>0) continue;
            db.sql("INSERT INTO market_sync(scope,status) VALUES(:scope,'UPDATING') ON CONFLICT(scope) DO UPDATE SET attempted_at=now(),status='UPDATING'").param("scope",scope).update();
            try {
                var stories=provider.research(theme.query(),theme.terms());
                jdbc.batchUpdate("""
                    INSERT INTO research_event(theme,headline,source,url,published_at,sentiment,fingerprint)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(theme,fingerprint) DO UPDATE SET sentiment=excluded.sentiment
                    """,stories,30,(ps,s)->{ps.setString(1,theme.id());ps.setString(2,s.headline());ps.setString(3,s.source());ps.setString(4,s.url());ps.setTimestamp(5,java.sql.Timestamp.from(s.published()));ps.setString(6,s.sentiment());ps.setString(7,s.fingerprint());});
                db.sql("UPDATE market_sync SET status='OK',succeeded_at=now(),detail=:detail WHERE scope=:scope")
                    .param("scope",scope).param("detail",stories.size()+" headlines checked").update();
            } catch(Exception e) {
                db.sql("UPDATE market_sync SET status='ERROR',detail='News refresh failed; saved headlines retained' WHERE scope=:scope").param("scope",scope).update();
                LoggerFactory.getLogger(getClass()).warn("Research refresh failed for {}: {}",theme.id(),e.toString());
            }
        }
    }
    public static String themeFor(String category) {
        String c=category.toLowerCase(Locale.ROOT);
        if(c.contains("bank")||c.contains("financial")) return "BANKING";
        if(c.contains("technology")||c.contains("information technology")||c.contains(" it ")) return "TECH";
        if(c.contains("energy")||c.contains("oil")) return "ENERGY";
        if(c.contains("pharma")||c.contains("health")) return "PHARMA";
        if(c.contains("auto")) return "AUTO";
        return "MACRO";
    }
}
