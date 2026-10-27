package com.moneyfest;

import com.fasterxml.jackson.databind.*;
import java.net.*;
import java.net.http.*;
import java.util.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("local")
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties={"spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://127.0.0.1:55432/moneyfest_test}","debug=false","moneyfest.market.enabled=false"})
class AccountPortfolioIntegrationTest {
    @LocalServerPort int port;
    @Autowired ObjectMapper json;
    @Autowired JdbcClient db;
    private Browser alice,bob;
    class Browser {
        final HttpClient client=HttpClient.newBuilder().cookieHandler(new CookieManager(null,CookiePolicy.ACCEPT_ALL)).build();
        HttpResponse<String> request(String method,String path,String body,boolean csrf) throws Exception {
            var builder=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/v1"+path)).header("Content-Type","application/json");
            if(csrf) {
                var token=json.readTree(request("GET","/auth/csrf",null,false).body());
                builder.header(token.get("headerName").asText(),token.get("token").asText());
            }
            return client.send(builder.method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(body)).build(),HttpResponse.BodyHandlers.ofString());
        }
        JsonNode get(String path) throws Exception {
            var response=request("GET",path,null,false); assertEquals(200,response.statusCode(),response.body()); return json.readTree(response.body());
        }
        void register(String email) throws Exception {
            var r=request("POST","/auth/register",json.writeValueAsString(Map.of("email",email,"password","strong-pass-123","displayName","Investor")),true);
            assertEquals(201,r.statusCode(),r.body());
        }
        void holding(String ticker,String qty,String cost) throws Exception {
            var r=request("PUT","/me/portfolio/positions",json.writeValueAsString(Map.of("ticker",ticker,"qty",qty,"avg_cost",cost)),true);
            assertEquals(200,r.statusCode(),r.body());
        }
    }
    @BeforeEach void setup() {
        assertTrue(db.sql("SELECT current_database()").query(String.class).single().endsWith("_test"),"Tests require a dedicated database ending in _test");
        db.sql("TRUNCATE app_user, price_bar, assessment, news_item, market_sync RESTART IDENTITY CASCADE").update();
        alice=new Browser(); bob=new Browser();
    }
    @AfterEach void cleanup() {
        if(db.sql("SELECT current_database()").query(String.class).single().endsWith("_test"))
            db.sql("TRUNCATE app_user,price_bar,assessment,spring_session,news_item,market_sync RESTART IDENTITY CASCADE").update();
    }
    @Test void accountLoginAndLogoutUsePersistentSession() throws Exception {
        alice.register("Alice@example.com");
        assertEquals("alice@example.com",alice.get("/auth/me").get("email").asText());
        assertTrue(db.sql("SELECT count(*) FROM spring_session_attributes WHERE attribute_name='SPRING_SECURITY_CONTEXT'").query(Long.class).single()>0);
        assertEquals(200,alice.request("POST","/auth/logout",null,true).statusCode());
        assertEquals(401,alice.request("GET","/auth/me",null,false).statusCode());
        assertEquals(401,alice.request("POST","/auth/login","{\"email\":\"alice@example.com\",\"password\":\"wrong-password\"}",true).statusCode());
        assertEquals(200,alice.request("POST","/auth/login","{\"email\":\"alice@example.com\",\"password\":\"strong-pass-123\"}",true).statusCode());
        assertEquals("alice@example.com",alice.get("/auth/me").get("email").asText());
    }
    @Test void personalHoldingsAreIsolatedAndUnknownFieldsRejected() throws Exception {
        alice.register("alice@example.com"); bob.register("bob@example.com");
        alice.holding("TCS","2.125","3000.05");
        assertEquals(1,alice.get("/me/portfolio").get("positions").size());
        assertEquals(0,bob.get("/me/portfolio").get("positions").size());
        assertEquals(400,bob.request("PUT","/me/portfolio/positions","{\"ticker\":\"TCS\",\"qty\":1,\"avg_cost\":1,\"user_id\":1}",true).statusCode());
        bob.request("DELETE","/me/portfolio/positions/TCS",null,true);
        assertEquals(1,alice.get("/me/portfolio").get("positions").size());
        alice.holding("TCS","3","2000");
        assertEquals(1,alice.get("/me/portfolio").get("positions").size());
        assertEquals(3,alice.get("/me/portfolio").get("positions").get(0).get("qty").asInt());
        assertEquals(200,alice.request("DELETE","/me/portfolio/positions/TCS",null,true).statusCode());
        assertEquals(0,alice.get("/me/portfolio").get("positions").size());
    }
    @Test void fundPortfolioIsOwnerScopedAndRequiresCsrf() throws Exception {
        alice.register("fund-alice@example.com"); bob.register("fund-bob@example.com");
        db.sql("INSERT INTO fund_scheme(code,name,plan,option_name,category,amc) VALUES('999991','Sample Banking Fund','Direct','Growth','Equity Scheme - Banking','Sample AMC') ON CONFLICT(code) DO NOTHING").update();
        db.sql("INSERT INTO fund_nav(code,date,nav) VALUES('999991',current_date-1,110.25) ON CONFLICT(code,date) DO UPDATE SET nav=excluded.nav").update();
        String body="{\"code\":\"999991\",\"units\":2,\"avg_nav\":100}";
        assertEquals(403,alice.request("PUT","/me/funds/positions",body,false).statusCode());
        assertEquals(200,alice.request("PUT","/me/funds/positions",body,true).statusCode());
        assertEquals(1,alice.get("/me/funds").get("positions").size());
        assertEquals(220.5,alice.get("/me/funds").get("value").asDouble(),0.00001);
        assertEquals(0,bob.get("/me/funds").get("positions").size());
        assertEquals(200,bob.request("DELETE","/me/funds/positions/999991",null,true).statusCode());
        assertEquals(1,alice.get("/me/funds").get("positions").size());
        assertEquals(1,alice.get("/funds?query=Sample%20Banking").get("items").size());
    }
    @Test void unpricedHoldingNeverLooksLikeZeroOrACompleteLoss() throws Exception {
        alice.register("alice@example.com"); alice.holding("TCS","2","3000");
        var portfolio=alice.get("/me/portfolio");
        assertEquals(6000,portfolio.get("total_invested").asInt());
        assertTrue(portfolio.get("total_value").isNull());
        assertTrue(portfolio.get("total_pnl").isNull());
        assertEquals(1,portfolio.get("unpriced_positions").asInt());
        assertTrue(portfolio.get("positions").get(0).get("price").isNull());
        assertEquals(0,alice.get("/me/portfolio/history").size());
    }
    @Test void pricedTotalsUseExactMoneyAndExcludeMissingPrices() throws Exception {
        alice.register("alice@example.com"); alice.holding("TCS","2","100.10"); alice.holding("INFY","1","50");
        db.sql("INSERT INTO price_bar(stock_id,date,close,source) SELECT id,current_date-1,110.10,'test' FROM stock WHERE ticker='TCS'").update();
        db.sql("INSERT INTO price_bar(stock_id,date,close,source) SELECT id,current_date,120.20,'test' FROM stock WHERE ticker='TCS'").update();
        var pf=alice.get("/me/portfolio");
        assertEquals(0,new java.math.BigDecimal("240.40").compareTo(pf.get("total_value").decimalValue()));
        assertEquals(0,new java.math.BigDecimal("40.20").compareTo(pf.get("total_pnl").decimalValue()));
        assertEquals(0,new java.math.BigDecimal("20.20").compareTo(pf.get("day_change").decimalValue()));
        assertEquals(1,pf.get("unpriced_positions").asInt());
        assertEquals(1,alice.get("/me/portfolio/allocation").get(0).get("weight").asInt());
        assertEquals(0.20079920,pf.get("total_pnl_pct").asDouble(),0.00000001);
        assertEquals(0,alice.get("/me/portfolio/history").size(),"Do not chart partially priced portfolios as complete");
    }
    @Test void csrfAndAuthenticationProtectMutations() throws Exception {
        assertEquals(401,alice.request("GET","/me/portfolio",null,false).statusCode());
        assertEquals(403,alice.request("POST","/auth/register","{}",false).statusCode());
        alice.register("alice@example.com");
        assertEquals(403,alice.request("PUT","/me/portfolio/positions","{\"ticker\":\"TCS\",\"qty\":1,\"avg_cost\":1}",false).statusCode());
        assertEquals(400,alice.request("PUT","/me/portfolio/positions","{\"ticker\":\"TCS\",\"qty\":-1,\"avg_cost\":1}",true).statusCode());
        assertEquals(400,alice.request("PUT","/me/portfolio/positions","{\"ticker\":\"TCS\",\"qty\":1,\"avg_cost\":\"NaN\"}",true).statusCode());
        assertEquals(404,alice.request("PUT","/me/portfolio/positions","{\"ticker\":\"MISSING\",\"qty\":1,\"avg_cost\":1}",true).statusCode());
    }
    @Test void savedPreferencesAndWatchlistsBelongToTheirOwner() throws Exception {
        alice.register("alice@example.com"); bob.register("bob@example.com");
        assertEquals(200,alice.request("PUT","/me/preferences","{\"alert_level\":\"HIGH_ONLY\",\"quiet_market\":true,\"daily_digest\":true}",true).statusCode());
        assertEquals("HIGH_ONLY",alice.get("/me/preferences").get("alert_level").asText());
        assertEquals("ALL",bob.get("/me/preferences").get("alert_level").asText());
        int stockId=alice.get("/stocks").get(0).get("stock_id").asInt();
        assertEquals(200,alice.request("PUT","/me/watchlist/"+stockId,null,true).statusCode());
        assertEquals(1,alice.get("/me/watchlist").size()); assertEquals(0,bob.get("/me/watchlist").size());
        assertEquals(200,alice.request("DELETE","/me/watchlist/"+stockId,null,true).statusCode());
        assertEquals(0,alice.get("/me/watchlist").size());
    }
    @Test void duplicateAccountsAndWeakPasswordsAreRejected() throws Exception {
        alice.register("alice@example.com");
        assertEquals(409,bob.request("POST","/auth/register","{\"email\":\"ALICE@example.com\",\"password\":\"strong-pass-123\"}",true).statusCode());
        assertEquals(400,bob.request("POST","/auth/register","{\"email\":\"bad@example.com\",\"password\":\"short\"}",true).statusCode());
        assertEquals(1,db.sql("SELECT count(*) FROM app_user").query(Long.class).single());
    }
    @Test void assessmentAndBoundedHistoryReportHonestMissingData() throws Exception {
        alice.register("alice@example.com");
        int id=alice.get("/stocks").get(0).get("stock_id").asInt();
        assertEquals("NOT_ASSESSED",alice.get("/stocks/"+id+"/assessment").get("outcome").asText());
        assertEquals("NOT_ASSESSED",alice.get("/stocks/"+id+"/assessment?date=2026-01-02").get("outcome").asText());
        assertEquals(400,alice.request("GET","/stocks/"+id+"/prices?days=9999",null,false).statusCode());
        assertEquals(404,alice.request("GET","/stocks/999999/prices",null,false).statusCode());
    }
    @Test void newsFeedFiltersByOwnershipAndReadState() throws Exception {
        alice.register("alice@example.com"); bob.register("bob@example.com");
        alice.holding("TCS","1","100");
        db.sql("INSERT INTO news_item(stock_id,headline,summary,url,source,published_at,sentiment,fingerprint) SELECT id,'TCS wins contract','TCS wins contract','https://example.com/story','Publisher',now(),'POSITIVE','fixture' FROM stock WHERE ticker='TCS'").update();
        var feed=alice.get("/me/news");
        assertEquals(1,feed.get("total").asInt()); assertEquals(1,feed.get("items").size());
        assertEquals(0,bob.get("/me/news").get("total").asInt());
        assertEquals(0,alice.get("/me/news?sentiment=NEGATIVE").get("total").asInt());
        long id=feed.get("items").get(0).get("id").asLong();
        assertEquals(403,alice.request("PUT","/me/news/"+id+"/read",null,false).statusCode());
        assertFalse(json.readTree(bob.request("PUT","/me/news/"+id+"/read",null,true).body()).get("ok").asBoolean());
        assertTrue(json.readTree(alice.request("PUT","/me/news/"+id+"/read",null,true).body()).get("ok").asBoolean());
        assertEquals(0,alice.get("/me/news?unread=true").get("total").asInt());
        assertEquals(1,alice.get("/me/news").get("total").asInt());
        assertEquals(400,alice.request("GET","/me/news?sentiment=BAD",null,false).statusCode());
        assertEquals(200,alice.request("POST","/me/refresh",null,true).statusCode());
        assertFalse(alice.get("/market/status").get("enabled").asBoolean());
    }
    @Test void stockSearchAndFiltersRunOnTheServer() throws Exception {
        alice.register("alice@example.com");
        var rows=alice.get("/stocks?query=consultancy");
        assertEquals(1,rows.size()); assertEquals("TCS",rows.get(0).get("ticker").asText());
        assertEquals(0,alice.get("/stocks?query=%25").size(),"Percent must be a literal search, not a wildcard");
        assertEquals(0,alice.get("/stocks?filter=held").size());
        alice.holding("TCS","1","100");
        assertEquals(1,alice.get("/stocks?filter=held").size());
        assertEquals(0,alice.get("/stocks?offset=10000").size());
        assertEquals(400,alice.request("GET","/stocks?offset=-1",null,false).statusCode());
    }
}
