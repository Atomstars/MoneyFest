package com.moneyfest.api.research;

import java.math.*;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController @RequestMapping("/api/v1/stocks")
class StockResearchController {
    private final JdbcClient db;
    StockResearchController(JdbcClient db) { this.db=db; }
    @GetMapping("/{id}/research") Map<String,Object> research(@PathVariable long id) {
        var stocks=db.sql("SELECT id,ticker,symbol,name,exchange,currency FROM stock WHERE id=:id").param("id",id).query().listOfRows();
        if(stocks.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Stock not found");
        var stock=stocks.getFirst();
        var bars=db.sql("SELECT date,close FROM price_bar WHERE stock_id=:id ORDER BY date DESC LIMIT 60").param("id",id).query().listOfRows();
        Map<String,Object> result=new LinkedHashMap<>();
        result.put("stock",stock); result.put("bars",bars); result.put("observations",bars.size());
        BigDecimal last=bars.isEmpty()?null:(BigDecimal)bars.getFirst().get("close");
        BigDecimal sma20=average(bars,20),sma50=average(bars,50);
        result.put("close",last); result.put("as_of",bars.isEmpty()?null:bars.getFirst().get("date"));
        result.put("sma20",sma20); result.put("sma50",sma50);
        result.put("trend",last==null || sma50==null?"INSUFFICIENT":last.compareTo(sma20)>0 && sma20.compareTo(sma50)>0?"UPTREND":last.compareTo(sma20)<0 && sma20.compareTo(sma50)<0?"DOWNTREND":"MIXED");
        result.put("change_pct",bars.size()<2?null:last.divide((BigDecimal)bars.get(1).get("close"),8,RoundingMode.HALF_UP).subtract(BigDecimal.ONE));
        result.put("news",db.sql("SELECT id,headline,source,url,published_at,sentiment FROM news_item WHERE stock_id=:id AND published_at>now()-interval '7 days' ORDER BY published_at DESC LIMIT 15").param("id",id).query().listOfRows());
        result.put("sync",db.sql("SELECT * FROM market_sync WHERE scope='prices:'||:id OR scope='news:'||:id ORDER BY scope").param("id",id).query().listOfRows());
        return result;
    }
    private static BigDecimal average(List<Map<String,Object>> bars,int count) {
        if(bars.size()<count) return null;
        return bars.stream().limit(count).map(b->(BigDecimal)b.get("close")).reduce(BigDecimal.ZERO,BigDecimal::add).divide(BigDecimal.valueOf(count),6,RoundingMode.HALF_UP);
    }
}
