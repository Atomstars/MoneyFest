package com.moneyfest;

import com.moneyfest.provider.MarketProvider;
import com.moneyfest.service.fund.FundService;
import com.moneyfest.service.research.ResearchService;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FundServiceTest {
    @Test void parsesCurrentAmfiColumnsAndSkipsInvalidNav() {
        String report="""
            Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date
            Open Ended Schemes(Equity Scheme - Sectoral/ Thematic)
            Example Mutual Fund
            123456;INF123A12345;-;Example Banking Fund;Direct Plan;Growth Option;123.4567;13-Oct-2026
            123457;INF123A12346;-;Example Banking Fund;Regular Plan;Growth Option;N.A.;13-Oct-2026
            """;
        var schemes=FundService.parse(report);
        assertEquals(1,schemes.size());
        assertEquals("123456",schemes.getFirst().code());
        assertEquals("Example Mutual Fund",schemes.getFirst().amc());
        assertEquals("Equity Scheme - Sectoral/ Thematic",schemes.getFirst().category());
        assertEquals("123.4567",schemes.getFirst().nav().toPlainString());
    }
    @Test void mapsExplicitFundCategoriesWithoutClaimingBroadFundExposure() {
        assertEquals("BANKING",ResearchService.themeFor("Equity Scheme - Banking"));
        assertEquals("MACRO",ResearchService.themeFor("Equity Scheme - Multi Cap Fund"));
    }
    @Test void newsToneClassifiesExplicitMarketMovesButNotAConditionalClaim() {
        assertEquals("POSITIVE",MarketProvider.sentiment("Electric passenger vehicle sales grow 95% YoY"));
        assertEquals("NEGATIVE",MarketProvider.sentiment("Vehicle sales fall after weak demand"));
        assertEquals("NEUTRAL",MarketProvider.sentiment("Auto stocks fall after RBI commentary"));
        assertEquals("NEUTRAL",MarketProvider.sentiment("Bank stocks could benefit if RBI holds rates"));
        assertEquals("NEUTRAL",MarketProvider.sentiment("RBI hikes interest rates by 25 bps"));
    }
}
