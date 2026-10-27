package com.moneyfest;

import com.moneyfest.provider.MarketProvider;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MarketProviderTest {
    @Test void usDirectoryExcludesEtfsAndTestIssuesAndNamespacesTickers() throws Exception {
        String data="Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
            +"AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
            +"QQQ|Index ETF|Q|N|N|100|Y|N\n"
            +"TEST|Test company|Q|Y|N|100|N|N\n"
            +"XYZW|Example Warrants|Q|N|N|100|N|N\nFile Creation Time: 10262026|||||||";
        var stocks=MarketProvider.parseUsCatalog(data,true);
        assertEquals(1,stocks.size()); assertEquals("AAPL.US",stocks.getFirst().ticker());
        assertEquals("AAPL",stocks.getFirst().providerSymbol());
        String other="ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\nBRK.B|Berkshire Hathaway Class B|N|BRK.B|N|100|N|BRK.B";
        assertEquals("BRK-B",MarketProvider.parseUsCatalog(other,false).getFirst().providerSymbol());
    }
    @Test void usPricesUseNewYorkDateAndSettlementAcrossDst() throws Exception {
        var json=new ObjectMapper().readTree("""
            {"chart":{"result":[{"meta":{"currency":"USD"},"timestamp":[1793280600,1793367000],
            "indicators":{"quote":[{"close":[100,110]}]}}]}}
            """);
        // Oct 29 and 30, 2026 at 09:30 New York; the second session is still open.
        var bars=MarketProvider.parsePrices(json,Instant.parse("2026-10-30T18:00:00Z"),"USD");
        assertEquals(1,bars.size()); assertEquals(LocalDate.parse("2026-10-29"),bars.getFirst().date());
        assertEquals(2,MarketProvider.parsePrices(json,Instant.parse("2026-10-30T21:00:00Z"),"USD").size());
        assertThrows(java.io.IOException.class,()->MarketProvider.parsePrices(json,Instant.now(),"INR"));
    }
    @Test void bseTradingGroupsAreEquitiesButDebtAndFundsAreNot() {
        assertTrue(MarketProvider.equityType("NSE","EQ"));
        for(String group:java.util.List.of("A","B","X","XT","M","MT","Z","TS")) assertTrue(MarketProvider.equityType("BSE",group));
        for(String group:java.util.List.of("F","G","E","IF")) assertFalse(MarketProvider.equityType("BSE",group));
        assertFalse(MarketProvider.equityType("NSE","FUT"));
    }
    @Test void pricesExcludeIntradayNullNegativeAndFutureBars() throws Exception {
        long yesterday=Instant.parse("2026-10-01T03:45:00Z").getEpochSecond();
        long today=Instant.parse("2026-10-02T03:45:00Z").getEpochSecond();
        String payload="""
            {"chart":{"result":[{"meta":{"currency":"INR"},"timestamp":[%d,%d,%d,%d],
            "indicators":{"quote":[{"close":[100.5,null,-2,101.5]}]}}]}}
            """.formatted(yesterday,yesterday,yesterday,today);
        var json=new ObjectMapper().readTree(payload);
        var morning=MarketProvider.parsePrices(json,Instant.parse("2026-10-02T05:00:00Z"));
        assertEquals(1,morning.size()); assertEquals(LocalDate.parse("2026-10-01"),morning.getFirst().date());
        assertEquals(2,MarketProvider.parsePrices(json,Instant.parse("2026-10-02T11:00:00Z")).size());
        assertThrows(java.io.IOException.class,()->MarketProvider.parsePrices(new ObjectMapper().readTree(payload.replace("INR","USD")),Instant.now()));
    }
    @Test void sentimentIsConservativeAboutNegationSpeculationAndConflictingEvents() {
        assertEquals("POSITIVE",MarketProvider.sentiment("Infosys wins contract"));
        assertEquals("NEGATIVE",MarketProvider.sentiment("Infosys profit falls"));
        assertEquals("MIXED",MarketProvider.sentiment("Infosys profit falls but wins contract"));
        assertEquals("NEUTRAL",MarketProvider.sentiment("Infosys denies fraud"));
        assertEquals("NEUTRAL",MarketProvider.sentiment("Infosys may win contract"));
        assertEquals("NEUTRAL",MarketProvider.sentiment("Infosys shares rise 4%"));
    }
    @Test void rssFiltersUnrelatedOldFutureStoriesAndDeduplicatesHeadlines() throws Exception {
        String xml="<rss><channel>"+item("Infosys wins contract - Publisher","Thu, 01 Oct 2026 08:00:00 GMT")
            +item("Infosys wins contract - Publisher","Thu, 01 Oct 2026 08:00:00 GMT")
            +item("Other Company profit falls","Thu, 01 Oct 2026 08:00:00 GMT")
            +item("Infosys profit falls","Mon, 01 Sep 2025 08:00:00 GMT")
            +item("Infosys wins order","Fri, 02 Oct 2026 08:00:00 GMT")+"</channel></rss>";
        var stories=MarketProvider.parseNews(xml.getBytes(StandardCharsets.UTF_8),"Infosys Limited","INFY",Instant.parse("2026-10-01T10:00:00Z"));
        assertEquals(1,stories.size()); assertEquals("Infosys wins contract",stories.getFirst().headline());
        assertFalse(MarketProvider.mentions("A new idea for investors","Vodafone Idea Limited","IDEA"));
        assertFalse(MarketProvider.mentions("TCSomething wins contract","Tata Consultancy Services","TCS"));
    }
    @Test void rssRejectsExternalEntities() {
        String xml="<!DOCTYPE rss [<!ENTITY xxe SYSTEM 'file:///should-not-be-read'>]><rss><channel>&xxe;</channel></rss>";
        assertThrows(Exception.class,()->MarketProvider.parseNews(xml.getBytes(StandardCharsets.UTF_8),"Infosys","INFY",Instant.now()));
    }
    private String item(String title,String date) { return "<item><title>"+title+"</title><source>Publisher</source><link>https://example.com/story</link><pubDate>"+date+"</pubDate></item>"; }
}
