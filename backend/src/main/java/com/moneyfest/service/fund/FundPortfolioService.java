package com.moneyfest.service.fund;

import com.moneyfest.repository.fund.FundPortfolioRepository;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class FundPortfolioService {
    public record Holding(String code, BigDecimal units, BigDecimal avgNav) {}

    private final FundPortfolioRepository funds;

    public FundPortfolioService(FundPortfolioRepository funds) { this.funds = funds; }

    public Map<String,Object> search(String email, String query, String category, int offset) {
        var rows=funds.search(funds.owner(email), query, category, offset);
        return Map.of("items",rows.subList(0,Math.min(40,rows.size())),"has_more",rows.size()>40);
    }

    public List<Map<String,Object>> categories() { return funds.categories(); }

    public Map<String,Object> discover(String email,String query,String group,int years,int offset) {
        return funds.discover(funds.owner(email),query,group,years,offset);
    }

    public List<Map<String,Object>> history(String code) { return funds.history(code); }

    @Transactional
    public Map<String,Object> put(String email, Holding in) {
        if (!funds.exists(in.code()))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Fund scheme not found in AMFI catalog");
        funds.upsert(funds.owner(email), in.code(), in.units(), in.avgNav());
        return Map.of("code", in.code());
    }

    public Map<String,Boolean> delete(String email, String code) {
        return Map.of("removed",funds.delete(funds.owner(email),code));
    }

    public Map<String,Object> portfolio(String email) {
        var rows=funds.positions(funds.owner(email));
        BigDecimal invested=BigDecimal.ZERO,value=BigDecimal.ZERO,pricedCost=BigDecimal.ZERO;
        int unpriced=0;
        for(var row:rows) {
            invested=invested.add((BigDecimal)row.get("invested"));
            if(row.get("value")==null) unpriced++;
            else { value=value.add((BigDecimal)row.get("value")); pricedCost=pricedCost.add((BigDecimal)row.get("invested")); }
        }
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("positions",rows);
        out.put("invested",invested);
        out.put("value",unpriced==rows.size()&&!rows.isEmpty()?null:value);
        out.put("pnl",unpriced==rows.size()&&!rows.isEmpty()?null:value.subtract(pricedCost));
        out.put("unpriced",unpriced);
        out.put("nav_source","AMFI daily NAV");
        out.put("sync",funds.syncStatus());
        return out;
    }
}
