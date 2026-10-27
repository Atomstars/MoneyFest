package com.moneyfest.service.fund;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/** Comparable Direct Growth returns, derived from official AMFI historical NAV reports. */
@Service
public class FundReturnService {
    public record Nav(String code, LocalDate date, BigDecimal value) {}
    private static final DateTimeFormatter DATE=DateTimeFormatter.ofPattern("dd-MMM-uuuu",Locale.ENGLISH);
    private final JdbcClient db;
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final boolean enabled;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).followRedirects(HttpClient.Redirect.NORMAL).build();
    public FundReturnService(JdbcClient db,JdbcTemplate jdbc,TransactionTemplate tx,@Value("${moneyfest.market.enabled:true}") boolean enabled) {
        this.db=db;this.jdbc=jdbc;this.tx=tx;this.enabled=enabled;
    }
    @Scheduled(initialDelay=35000,fixedDelay=3600000)
    void sync() {
        if(!enabled) return;
        if(db.sql("SELECT count(*) FROM market_sync WHERE scope='funds:returns' AND succeeded_at>now()-interval '12 hours'").query(Long.class).single()>0) return;
        db.sql("INSERT INTO market_sync(scope,status) VALUES('funds:returns','UPDATING') ON CONFLICT(scope) DO UPDATE SET attempted_at=now(),status='UPDATING',detail=NULL").update();
        try {
            var latest=db.sql("""
                SELECT f.code,n.date,n.nav FROM fund_scheme f
                JOIN LATERAL(SELECT date,nav FROM fund_nav WHERE code=f.code ORDER BY date DESC LIMIT 1) n ON true
                WHERE f.active AND lower(f.plan) LIKE '%direct%' AND lower(f.option_name) LIKE '%growth%'
                AND n.date>=current_date-10 AND n.date<=current_date
                """).query((rs,i)->new Nav(rs.getString(1),rs.getObject(2,LocalDate.class),rs.getBigDecimal(3))).list();
            if(latest.size()<500) throw new IOException("Current AMFI catalog not yet available");
            LocalDate asof=latest.stream().map(Nav::date).max(LocalDate::compareTo).orElseThrow();
            List<Map<String,Nav>> anchors=new ArrayList<>();
            for(int years:new int[]{1,3}) {
                LocalDate end=asof.minusYears(years),start=end.minusDays(16);
                String url="https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?tp=1&frmdt="+DATE.format(start)+"&todt="+DATE.format(end);
                var points=download(url);
                Map<String,Nav> byCode=new HashMap<>();
                for(Nav n:points) if(!n.date().isAfter(end)&&!n.date().isBefore(start)) byCode.merge(n.code(),n,(a,b)->a.date().isAfter(b.date())?a:b);
                anchors.add(byCode);
            }
            tx.executeWithoutResult(status->jdbc.batchUpdate("""
                INSERT INTO fund_return_snapshot(code,nav_date,nav,return_1y,return_3y,return_5y,anchor_1y,anchor_3y,anchor_5y)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET nav_date=excluded.nav_date,nav=excluded.nav,
                return_1y=excluded.return_1y,return_3y=excluded.return_3y,return_5y=excluded.return_5y,
                anchor_1y=excluded.anchor_1y,anchor_3y=excluded.anchor_3y,anchor_5y=excluded.anchor_5y,updated_at=now()
                """,latest,500,(ps,n)->{
                    ps.setString(1,n.code());ps.setObject(2,n.date());ps.setBigDecimal(3,n.value());
                    ps.setObject(6,null);ps.setObject(9,null);
                    int[] periods={1,3};
                    for(int i=0;i<2;i++) {
                        Nav a=anchors.get(i).get(n.code());
                        Double result=returns(n,a,periods[i]);
                        ps.setObject(4+i,result);ps.setObject(7+i,result==null?null:a.date());
                    }
                }));
            db.sql("UPDATE market_sync SET status='OK',succeeded_at=now(),detail=:detail WHERE scope='funds:returns'").param("detail",latest.size()+" Direct Growth schemes checked against AMFI historical NAV").update();
        } catch(Exception e) {
            db.sql("UPDATE market_sync SET status='ERROR',detail='Historical returns refresh unavailable; saved returns retained' WHERE scope='funds:returns'").update();
            LoggerFactory.getLogger(getClass()).warn("Fund return sync failed: {}",e.toString());
            if(e instanceof InterruptedException) Thread.currentThread().interrupt();
        }
    }
    private List<Nav> download(String url) throws IOException,InterruptedException {
        IOException failure=new IOException("Historical AMFI report unavailable");
        for(int attempt=0;attempt<3;attempt++) {
            try {
                var response=http.send(HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(60)).header("User-Agent","Moneyfest/1.0").GET().build(),HttpResponse.BodyHandlers.ofByteArray());
                if(response.statusCode()!=200||response.body().length>30_000_000) throw new IOException("Historical AMFI HTTP "+response.statusCode()+", bytes "+response.body().length);
                var points=parseHistory(new String(response.body(),StandardCharsets.UTF_8));
                if(points.size()<1000) throw new IOException("Incomplete historical AMFI report");
                return points;
            } catch(IOException e) { failure=e; }
            if(attempt<2) Thread.sleep(1000L*(attempt+1));
        }
        throw failure;
    }
    public static Double returns(Nav latest,Nav anchor,int years) {
        if(anchor==null||!latest.code().equals(anchor.code())||anchor.value().signum()<=0||latest.value().signum()<=0) return null;
        long gap=ChronoUnit.DAYS.between(anchor.date(),latest.date().minusYears(years));
        if(gap<0||gap>10) return null;
        double ratio=latest.value().doubleValue()/anchor.value().doubleValue();
        double value=(years==1?ratio-1:Math.pow(ratio,365.25/ChronoUnit.DAYS.between(anchor.date(),latest.date()))-1)*100;
        return Double.isFinite(value)?value:null;
    }
    public static List<Nav> parseHistory(String report) {
        List<Nav> out=new ArrayList<>();
        // AMFI history uses NAV Name/Plan/Option before ISIN, unlike the daily report.
        if(!report.startsWith("Scheme Code;NAV Name;Plan;Option;")) return out;
        var lines=report.lines().iterator();
        while(lines.hasNext()) {
            String line=lines.next();
            String[] p=line.split(";",-1);
            if(p.length!=8||!p[0].matches("\\d{3,10}")) continue;
            try {
                var nav=new BigDecimal(p[6].trim());var date=LocalDate.parse(p[7].trim(),DATE);
                if(nav.signum()>0&&!date.isAfter(LocalDate.now())) out.add(new Nav(p[0],date,nav));
            } catch(RuntimeException ignored) { }
        }
        return out;
    }
}
