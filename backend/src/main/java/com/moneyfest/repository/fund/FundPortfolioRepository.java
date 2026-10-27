package com.moneyfest.repository.fund;

import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class FundPortfolioRepository {
    private final JdbcClient db;

    public FundPortfolioRepository(JdbcClient db) { this.db = db; }

    public long owner(String email) {
        return db.sql("SELECT id FROM app_user WHERE email=:email").param("email", email).query(Long.class).single();
    }

    public List<Map<String,Object>> search(long userId, String query, String category, int offset) {
        String needle="%"+query.trim().toLowerCase(Locale.ROOT).replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%";
        return db.sql("""
            SELECT f.code,f.name,f.amc,f.category,f.plan,f.option_name,f.isin,
              n.date,n.nav,previous.nav AS previous_nav,
              EXISTS(SELECT 1 FROM fund_position p WHERE p.code=f.code AND p.user_id=:uid) AS held
            FROM fund_scheme f
            LEFT JOIN LATERAL (SELECT date,nav FROM fund_nav WHERE code=f.code ORDER BY date DESC LIMIT 1) n ON true
            LEFT JOIN LATERAL (SELECT nav FROM fund_nav WHERE code=f.code AND date<n.date ORDER BY date DESC LIMIT 1) previous ON true
            WHERE f.active AND (lower(f.name||' '||f.amc||' '||f.category||' '||f.code) LIKE :query ESCAPE '\\')
              AND (:category='' OR f.category=:category)
            ORDER BY held DESC,f.name,f.plan,f.option_name LIMIT 41 OFFSET :offset
            """).param("uid",userId).param("query",needle).param("category",category).param("offset",offset).query().listOfRows();
    }

    public List<Map<String,Object>> categories() {
        return db.sql("SELECT category,count(*) AS schemes FROM fund_scheme WHERE active GROUP BY category ORDER BY category").query().listOfRows();
    }

    public Map<String,Object> discover(long userId,String query,String group,int years,int offset) {
        String metric=years==1?"return_1y":"return_3y";
        String needle="%"+query.trim().toLowerCase(Locale.ROOT).replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%";
        String base="""
            FROM fund_discovery_scheme f
            JOIN LATERAL(SELECT date,nav FROM fund_nav WHERE code=f.code ORDER BY date DESC LIMIT 1) n ON true
            LEFT JOIN fund_return_snapshot r ON r.code=f.code AND r.nav_date=n.date
            WHERE f.active AND lower(f.plan) LIKE '%direct%' AND lower(f.option_name) LIKE '%growth%'
            AND n.date>=current_date-10 AND n.date<=current_date
            """;
        String filter=" AND (:group='' OR f.group_id=:group) AND lower(f.name||' '||f.amc||' '||f.code) LIKE :query ESCAPE '\\'";
        var rows=db.sql("""
            SELECT f.code,f.name,f.amc,f.category,f.plan,f.option_name,f.isin,f.group_id,n.date,n.nav,
            NULL::numeric AS previous_nav,r.return_1y,r.return_3y,r.return_5y,
            r.anchor_1y,r.anchor_3y,r.anchor_5y,
            EXISTS(SELECT 1 FROM fund_position p WHERE p.code=f.code AND p.user_id=:uid) AS held
            """+base+filter+" ORDER BY r."+metric+" DESC NULLS LAST,f.code LIMIT 41 OFFSET :offset")
            .param("uid",userId).param("group",group).param("query",needle).param("offset",offset).query().listOfRows();
        var counts=db.sql("SELECT count(*) AS total,count(r."+metric+") AS ranked,max(n.date) AS as_of "+base+filter)
            .param("group",group).param("query",needle).query().singleRow();
        var groups=db.sql("SELECT f.group_id,count(*) AS schemes "+base+" GROUP BY f.group_id").query().listOfRows();
        var status=db.sql("SELECT status,detail,succeeded_at FROM market_sync WHERE scope='funds:returns'").query().listOfRows();
        return Map.of("items",rows.subList(0,Math.min(40,rows.size())),"has_more",rows.size()>40,
            "summary",counts,"groups",groups,"sync",status,"period",years);
    }

    public List<Map<String,Object>> history(String code) {
        return db.sql("SELECT date,nav FROM fund_nav WHERE code=:code ORDER BY date DESC LIMIT 180").param("code",code).query().listOfRows();
    }

    public boolean exists(String code) {
        return db.sql("SELECT count(*) FROM fund_scheme WHERE code=:code").param("code",code).query(Long.class).single()>0;
    }

    public void upsert(long userId, String code, BigDecimal units, BigDecimal avgNav) {
        db.sql("""
            INSERT INTO fund_position(user_id,code,units,avg_nav) VALUES(:uid,:code,:units,:nav)
            ON CONFLICT(user_id,code) DO UPDATE SET units=excluded.units,avg_nav=excluded.avg_nav,updated_at=now()
            """).param("uid",userId).param("code",code).param("units",units).param("nav",avgNav).update();
    }

    public boolean delete(long userId, String code) {
        return db.sql("DELETE FROM fund_position WHERE user_id=:uid AND code=:code").param("uid",userId).param("code",code).update()>0;
    }

    public List<Map<String,Object>> positions(long userId) {
        return db.sql("""
            SELECT f.code,f.name,f.amc,f.category,f.plan,f.option_name,p.units,p.avg_nav,
              n.date,n.nav,p.units*p.avg_nav AS invested,p.units*n.nav AS value
            FROM fund_position p JOIN fund_scheme f ON f.code=p.code
            LEFT JOIN LATERAL (SELECT date,nav FROM fund_nav WHERE code=p.code ORDER BY date DESC LIMIT 1) n ON true
            WHERE p.user_id=:uid ORDER BY f.name
            """).param("uid",userId).query().listOfRows();
    }

    public List<Map<String,Object>> syncStatus() {
        return db.sql("SELECT status,detail,succeeded_at FROM market_sync WHERE scope='funds:amfi'").query().listOfRows();
    }
}
