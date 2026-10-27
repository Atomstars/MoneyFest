package com.moneyfest.api.research;

import com.moneyfest.service.research.ResearchService;

import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/v1/research")
class ResearchController {
    private final JdbcClient db;
    ResearchController(JdbcClient db) { this.db=db; }
    @GetMapping("/themes") List<Map<String,Object>> themes() {
        List<Map<String,Object>> result=new ArrayList<>();
        for(var theme:ResearchService.THEMES) {
            var events=db.sql("""
                SELECT headline,source,url,published_at,sentiment FROM research_event
                WHERE theme=:theme AND published_at>now()-interval '7 days'
                ORDER BY published_at DESC LIMIT 12
                """).param("theme",theme.id()).query().listOfRows();
            long positive=events.stream().filter(e->"POSITIVE".equals(e.get("sentiment"))).count();
            long negative=events.stream().filter(e->"NEGATIVE".equals(e.get("sentiment"))).count();
            String signal=positive+negative<2?"INSUFFICIENT":positive>negative?"POSITIVE":negative>positive?"NEGATIVE":"MIXED";
            String focus=focus(theme.id(),events);
            Map<String,Object> row=new LinkedHashMap<>();
            row.put("id",theme.id());row.put("label",theme.label());row.put("signal",signal);
            row.put("positive",positive);row.put("negative",negative);row.put("events",events);
            row.put("focus",focus);
            row.put("sync",db.sql("SELECT status,succeeded_at,detail FROM market_sync WHERE scope=:scope")
                .param("scope","research:"+theme.id()).query().listOfRows());
            result.add(row);
        }
        return result;
    }
    static String focus(String theme,List<Map<String,Object>> events) {
        Map<String,String[]> topics=Map.of(
            "BANKING",new String[]{"rate|rbi|liquidity","Rates and RBI policy"},
            "TECH",new String[]{"ai|software|demand|export","Technology demand"},
            "ENERGY",new String[]{"oil|crude|fuel","Oil and fuel prices"},
            "PHARMA",new String[]{"drug|approval|pharma","Drug and pharma news"},
            "AUTO",new String[]{"sales|vehicle|ev|auto","Vehicle demand"},
            "MACRO",new String[]{"inflation|tariff|global|fii","Macro policy and flows"});
        String[] topic=topics.get(theme);
        if(topic==null) return null;
        long count=events.stream().filter(e->java.util.regex.Pattern.compile("(?i)\\b("+topic[0]+")\\b")
            .matcher(Objects.toString(e.get("headline"),"")).find()).count();
        return count>=2?topic[1]:null;
    }
}
