package com.moneyfest;

import com.moneyfest.repository.fund.FundPortfolioRepository;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;

@ActiveProfiles("local")
@SpringBootTest(properties={"spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://127.0.0.1:55432/moneyfest_test}","moneyfest.market.enabled=false","test.scope=fund-rankings","debug=false"})
@Transactional
class FundRankingIntegrationTest {
    @Autowired JdbcClient db;
    @Autowired FundPortfolioRepository funds;
    void seed(int id,String name,String category,String plan,String option,Double value) {
        assertTrue(db.sql("SELECT current_database()").query(String.class).single().endsWith("_test"));
        String code=String.valueOf(id);
        db.sql("INSERT INTO fund_scheme(code,name,amc,category,plan,option_name) VALUES(:code,:name,'RankSpec AMC',:category,:plan,:option)")
            .param("code",code).param("name",name).param("category",category).param("plan",plan).param("option",option).update();
        db.sql("INSERT INTO fund_nav(code,date,nav) VALUES(:code,current_date,100)").param("code",code).update();
        if(value!=null) db.sql("INSERT INTO fund_return_snapshot(code,nav_date,nav,return_1y,return_3y,return_5y) VALUES(:code,current_date,100,:r,:r3,:r5)")
            .param("code",code).param("r",-value).param("r3",value/2).param("r5",-value).update();
    }
    @SuppressWarnings("unchecked") List<Map<String,Object>> rows(Map<String,Object> result) { return (List<Map<String,Object>>)result.get("items"); }
    @Test void ranksWholeFilteredUniverseBeforePaginationAndLeavesMissingHistoryLast() {
        for(int i=0;i<43;i++) seed(990100+i,"RankSpec "+(char)('Z'-i%26)+i,"Equity Scheme - Mid Cap Fund","Direct","Growth",(double)i);
        seed(990199,"RankSpec A Missing","Equity Scheme - Mid Cap Fund","Direct","Growth",null);
        seed(990198,"RankSpec Regular","Equity Scheme - Mid Cap Fund","Regular","Growth",999.0);
        seed(990197,"RankSpec IDCW","Equity Scheme - Mid Cap Fund","Direct","IDCW",999.0);
        var first=funds.discover(-1,"RankSpec","mid",3,0);
        assertEquals(40,rows(first).size());assertEquals(true,first.get("has_more"));
        assertEquals("990142",rows(first).getFirst().get("code"));
        var second=funds.discover(-1,"RankSpec","mid",3,40);
        assertEquals(4,rows(second).size());assertEquals("990199",rows(second).getLast().get("code"));
        assertNull(rows(second).getLast().get("return_3y"));
        assertEquals("990100",rows(funds.discover(-1,"RankSpec","mid",1,0)).getFirst().get("code"));
        assertTrue(rows(funds.discover(-1,"RankSpec%","mid",3,0)).isEmpty());
    }
    @Test void categoryBoundariesAndNavDatesAreRespected() {
        seed(990201,"RankSpec Large","Equity Scheme - Large Cap Fund","Direct","Growth",5.0);
        seed(990202,"RankSpec Both","Equity Scheme - Large & Mid Cap Fund","Direct","Growth",10.0);
        seed(990203,"RankSpec Index","Index Funds - Equity Funds","Direct","Growth",15.0);
        assertEquals("990201",rows(funds.discover(-1,"RankSpec","large",3,0)).getFirst().get("code"));
        assertEquals(1,rows(funds.discover(-1,"RankSpec","large",3,0)).size());
        assertEquals("990202",rows(funds.discover(-1,"RankSpec","large-mid",3,0)).getFirst().get("code"));
        assertEquals("990203",rows(funds.discover(-1,"RankSpec","index",3,0)).getFirst().get("code"));
        db.sql("UPDATE fund_return_snapshot SET nav_date=current_date-1 WHERE code='990201'").update();
        assertNull(rows(funds.discover(-1,"RankSpec","large",3,0)).getFirst().get("return_3y"));
    }
}
