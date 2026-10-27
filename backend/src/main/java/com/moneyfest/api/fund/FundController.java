package com.moneyfest.api.fund;

import com.moneyfest.service.fund.FundPortfolioService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.security.Principal;
import java.util.List;
import java.util.Map;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController
@Validated
@RequestMapping("/api/v1")
class FundController {
    private final FundPortfolioService funds;

    FundController(FundPortfolioService funds) { this.funds = funds; }

    @GetMapping("/funds")
    Map<String,Object> search(Principal user, @RequestParam(defaultValue="") @Size(max=100) String query,
        @RequestParam(defaultValue="") @Size(max=100) String category,
        @RequestParam(defaultValue="0") @Min(0) @Max(100000) int offset) {
        return funds.search(user.getName(), query, category, offset);
    }

    @GetMapping("/funds/categories")
    List<Map<String,Object>> categories() { return funds.categories(); }

    @GetMapping("/funds/discover")
    Map<String,Object> discover(Principal user,@RequestParam(defaultValue="") @Size(max=100) String query,
        @RequestParam(defaultValue="") @Pattern(regexp="|large|mid|small|flexi|multi|large-mid|index|elss|debt|hybrid|sector|other") String group,
        @RequestParam(defaultValue="3") @Pattern(regexp="1|3") String period,
        @RequestParam(defaultValue="0") @Min(0) @Max(100000) int offset) {
        return funds.discover(user.getName(),query,group,Integer.parseInt(period),offset);
    }

    @GetMapping("/funds/{code}/nav")
    List<Map<String,Object>> history(@PathVariable @Pattern(regexp="\\d{3,10}") String code) {
        return funds.history(code);
    }

    record Holding(@NotNull @Pattern(regexp="\\d{3,10}") String code,
        @NotNull @DecimalMin(value="0",inclusive=false) @Digits(integer=14,fraction=6) BigDecimal units,
        @NotNull @DecimalMin("0") @Digits(integer=14,fraction=6) BigDecimal avg_nav) {}

    @PutMapping("/me/funds/positions")
    Map<String,Object> put(Principal user, @Valid @RequestBody Holding in) {
        return funds.put(user.getName(), new FundPortfolioService.Holding(in.code(), in.units(), in.avg_nav()));
    }

    @DeleteMapping("/me/funds/positions/{code}")
    Map<String,Boolean> delete(Principal user, @PathVariable @Pattern(regexp="\\d{3,10}") String code) {
        return funds.delete(user.getName(), code);
    }

    @GetMapping("/me/funds")
    Map<String,Object> portfolio(Principal user) { return funds.portfolio(user.getName()); }
}
