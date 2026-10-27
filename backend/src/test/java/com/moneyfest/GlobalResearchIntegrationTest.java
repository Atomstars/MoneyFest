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
    properties={"spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://127.0.0.1:55432/moneyfest_test}","debug=false","moneyfest.market.enabled=false","moneyfest.test.scope=global"})
class GlobalResearchIntegrationTest {
    @Test void usHoldingsNeverMixIntoInrTotalsAndResearchUsesSavedSessions() throws Exception {
        alice.register("global@example.com"); alice.holding("TCS","2","100"); alice.holding("AAPL.US","3","10");
        assertEquals(200,alice.get("/me/portfolio").get("total_invested").asInt());
        var usd=alice.get("/me/portfolio?currency=USD");
        assertEquals("USD",usd.get("currency").asText()); assertEquals(30,usd.get("total_invested").asInt());
        assertEquals(1,usd.get("positions").size());
        var stock=alice.get("/stocks?market=US&query=AAPL").get(0);
        long id=stock.get("stock_id").asLong();
        assertEquals("USD",stock.get("currency").asText());
        assertEquals(0,alice.get("/stocks?market=IN&query=AAPL").size());
        assertEquals("INSUFFICIENT",alice.get("/stocks/"+id+"/research").get("trend").asText());
        db.sql("INSERT INTO price_bar(stock_id,date,close,source) SELECT :id,current_date-60+i,100+i,'fixture' FROM generate_series(1,60) i").param("id",id).update();
        var research=alice.get("/stocks/"+id+"/research");
        assertEquals("UPTREND",research.get("trend").asText()); assertEquals(60,research.get("observations").asInt());
        assertEquals(480,alice.get("/me/portfolio?currency=USD").get("total_value").asInt());
        assertEquals(0,alice.get("/me/portfolio/history").size());
        assertEquals(60,alice.get("/me/portfolio/history?currency=USD").size());
    }
    @Test void portfolioPlansArePrivateValidatedAndSupportRulesReview() throws Exception {
        alice.register("plan-alice@example.com");bob.register("plan-bob@example.com");
        long apple=alice.get("/stocks?market=US&query=AAPL").get(0).get("stock_id").asLong();
        long tcs=alice.get("/stocks?market=IN&query=TCS").get(0).get("stock_id").asLong();
        String body="{\"currency\":\"USD\",\"risk\":\"CAUTIOUS\",\"horizon_years\":3,\"budget\":1000,\"allocations\":[{\"stock_id\":"+apple+",\"weight\":60}]}";
        assertEquals(403,alice.request("PUT","/me/portfolio-plan",body,false).statusCode());
        assertEquals(200,alice.request("PUT","/me/portfolio-plan",body,true).statusCode());
        assertEquals(1,alice.get("/me/portfolio-plan").get("stocks").size());
        assertFalse(bob.get("/me/portfolio-plan").get("saved").asBoolean());
        assertEquals(400,alice.request("PUT","/me/portfolio-plan",body.replace("\"weight\":60","\"weight\":101"),true).statusCode());
        assertEquals(400,alice.request("PUT","/me/portfolio-plan",body.replace("\"stock_id\":"+apple,"\"stock_id\":"+tcs),true).statusCode());
        var review=alice.request("POST","/me/portfolio-plan/review","{\"question\":\"What is the best portfolio?\"}",true);
        assertEquals(200,review.statusCode(),review.body());assertTrue(review.body().contains("cannot rank securities"));
        assertTrue(review.body().contains("AAPL"));
        assertEquals(0,alice.get("/me/portfolio?currency=USD").get("positions").size());
    }
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
}
