package com.moneyfest;

import com.moneyfest.service.fund.FundReturnService;
import com.moneyfest.service.fund.FundReturnService.Nav;
import java.math.BigDecimal;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FundReturnTest {
    Nav nav(String code,String date,String value) { return new Nav(code,LocalDate.parse(date),new BigDecimal(value)); }
    @Test void computesAbsoluteOneYearAndAnnualisedMultiYearReturns() {
        var current=nav("123456","2026-10-26","133.1");
        assertEquals(33.1,FundReturnService.returns(current,nav("123456","2025-10-24","100"),1),0.00001);
        assertEquals(10,FundReturnService.returns(current,nav("123456","2023-10-26","100"),3),0.01);
        assertEquals(-10,FundReturnService.returns(nav("123456","2026-10-26","90"),nav("123456","2025-10-24","100"),1),0.00001);
    }
    @Test void rejectsMissingMismatchedStaleAndTooShortHistory() {
        var current=nav("123456","2026-10-26","133.1");
        assertNull(FundReturnService.returns(current,null,3));
        assertNull(FundReturnService.returns(current,nav("654321","2023-10-26","100"),3));
        assertNull(FundReturnService.returns(current,nav("123456","2023-09-26","100"),3));
        assertNull(FundReturnService.returns(current,nav("123456","2023-10-27","100"),3));
        assertNull(FundReturnService.returns(current,nav("123456","2023-10-26","0"),3));
    }
    @Test void parsesHistoryColumnOrderAndRejectsHtmlOrInvalidNav() {
        String report="""
            Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date
            123456;Example;Direct;Growth;;;100.25;26-Oct-2023
            123457;Example;Direct;Growth;;;N.A.;26-Oct-2023
            123458;Example;Direct;Growth;;;0;26-Oct-2023
            123459;Example;Direct;Growth;;;100;26-Oct-2099
            """;
        var rows=FundReturnService.parseHistory(report);
        assertEquals(1,rows.size());
        assertEquals(new BigDecimal("100.25"),rows.getFirst().value());
        assertTrue(FundReturnService.parseHistory("<html>error</html>").isEmpty());
    }
}
