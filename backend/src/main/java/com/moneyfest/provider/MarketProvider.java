package com.moneyfest.provider;

import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.*;
import java.io.*;
import java.math.BigDecimal;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.regex.Pattern;
import java.util.function.Predicate;
import java.util.zip.GZIPInputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.springframework.stereotype.Component;
import org.w3c.dom.*;

/** Public, best-effort adapters. No credentials, fabricated prices, or inferred BSE codes. */
@Component
public class MarketProvider {
    public static final ZoneId INDIA=ZoneId.of("Asia/Kolkata");
    private final ObjectMapper json;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).followRedirects(HttpClient.Redirect.NORMAL).build();
    MarketProvider(ObjectMapper json) { this.json=json; }
    public record Instrument(String ticker,String symbol,String name,String exchange,String isin,String providerSymbol) {}
    public record Bar(LocalDate date,BigDecimal close) {}
    public record Story(String headline,String url,String source,Instant published,String sentiment,String fingerprint) {}

    private byte[] fetch(String url) throws Exception {
        var request=HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(25))
            .header("User-Agent","Mozilla/5.0 Moneyfest/1.0").GET().build();
        var response=http.send(request,HttpResponse.BodyHandlers.ofByteArray());
        if(response.statusCode()!=200) throw new IOException("Provider returned HTTP "+response.statusCode());
        if(response.body().length>30_000_000) throw new IOException("Provider response too large");
        return response.body();
    }
    public List<Instrument> catalog(String exchange) throws Exception {
        byte[] data=fetch("https://assets.upstox.com/market-quote/instruments/exchange/"+exchange+".json.gz");
        try(var input=new GZIPInputStream(new ByteArrayInputStream(data)); var parser=json.getFactory().createParser(input)) {
            List<Instrument> result=new ArrayList<>();
            if(parser.nextToken()!=JsonToken.START_ARRAY) throw new IOException("Invalid instrument catalog");
            while(parser.nextToken()==JsonToken.START_OBJECT) {
                JsonNode n=json.readTree(parser);
                if(!n.path("segment").asText().equals(exchange+"_EQ") || !equityType(exchange,n.path("instrument_type").asText())) continue;
                String symbol=n.path("trading_symbol").asText(), name=n.path("name").asText(), isin=n.path("isin").asText();
                String ticker=symbol+(exchange.equals("BSE")?".BSE":"");
                String provider=exchange.equals("NSE")?symbol+".NS":n.path("exchange_token").asText()+".BO";
                if(symbol.isBlank() || ticker.length()>30 || name.isBlank() || !isin.matches("IN[A-Z0-9]{10}")) continue;
                if(exchange.equals("BSE") && !n.path("exchange_token").asText().matches("[0-9]{6}")) continue;
                result.add(new Instrument(ticker,symbol,name.substring(0,Math.min(160,name.length())),exchange,isin,provider));
            }
            if(result.size()<100) throw new IOException("Incomplete instrument catalog");
            return result;
        }
    }
    public List<Instrument> usCatalog() throws Exception {
        List<Instrument> all=new ArrayList<>();
        all.addAll(parseUsCatalog(new String(fetch("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"),StandardCharsets.UTF_8),true));
        all.addAll(parseUsCatalog(new String(fetch("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"),StandardCharsets.UTF_8),false));
        if(all.size()<1000) throw new IOException("Incomplete US instrument catalog");
        return all;
    }
    public static List<Instrument> parseUsCatalog(String text,boolean nasdaq) throws IOException {
        String[] lines=text.split("\\R");
        if(lines.length==0 || !lines[0].startsWith(nasdaq?"Symbol|Security Name|":"ACT Symbol|Security Name|")) throw new IOException("Invalid US directory");
        List<Instrument> result=new ArrayList<>();
        for(int i=1;i<lines.length;i++) {
            String[] c=lines[i].split("\\|",-1);
            if(c.length<8 || !c[nasdaq?3:6].equals("N") || !c[nasdaq?6:4].equals("N")) continue;
            String symbol=c[0],name=c[1];
            String exchange=nasdaq?"NASDAQ":Map.of("N","NYSE","A","AMEX","P","ARCA","Z","BATS","V","IEX").get(c[2]);
            // Retain ordinary shares/ADRs; omit preferreds, rights, warrants, units and funds.
            if(exchange==null || !symbol.matches("[A-Z]{1,5}(\\.[AB])?") || name.isBlank()
                || Pattern.compile("(?i)warrant|preferred|depositary shares|units|rights|fund| ETF").matcher(name).find()) continue;
            result.add(new Instrument(symbol+".US",symbol,name.substring(0,Math.min(160,name.length())),exchange,null,symbol.replace('.','-')));
        }
        return result;
    }
    public static boolean equityType(String exchange,String type) {
        // BSE uses trading groups, not NSE's EQ code. Exclude debt (F/G), ETFs (E), and funds (IF).
        return exchange.equals("NSE") ? type.equals("EQ") : Set.of("A","B","T","X","XT","Z","ZP","M","MT","TS","MS","P","W","D","DT","IT","SS","ST","S","XC","XD").contains(type);
    }
    public List<Bar> prices(String symbol) throws Exception { return prices(symbol,"INR"); }
    public List<Bar> prices(String symbol,String currency) throws Exception {
        return parsePrices(json.readTree(fetch("https://query1.finance.yahoo.com/v8/finance/chart/"+encode(symbol)+"?interval=1d&range=6mo")),Instant.now(),currency);
    }
    public static List<Bar> parsePrices(JsonNode root,Instant now) throws IOException {
        return parsePrices(root,now,"INR");
    }
    public static List<Bar> parsePrices(JsonNode root,Instant now,String currency) throws IOException {
        JsonNode result=root.path("chart").path("result").path(0);
        if(!Set.of("INR","USD").contains(currency) || !result.path("meta").path("currency").asText().equals(currency)) throw new IOException("Missing or mismatched price currency");
        ZoneId zone=currency.equals("USD")?ZoneId.of("America/New_York"):INDIA;
        LocalTime settled=currency.equals("USD")?LocalTime.of(16,30):LocalTime.of(16,0);
        JsonNode timestamps=result.path("timestamp"), closes=result.path("indicators").path("quote").path(0).path("close");
        var today=now.atZone(zone);
        List<Bar> bars=new ArrayList<>();
        for(int i=0;i<timestamps.size();i++) {
            LocalDate date=Instant.ofEpochSecond(timestamps.get(i).asLong()).atZone(zone).toLocalDate();
            // Intraday bars are not closing prices. Allow a settlement buffer after 15:30 IST.
            if(date.isAfter(today.toLocalDate()) || (date.equals(today.toLocalDate()) && today.toLocalTime().isBefore(settled))) continue;
            JsonNode close=closes.path(i);
            if(!close.isNumber() || !Double.isFinite(close.asDouble()) || close.asDouble()<=0 || close.asDouble()>=1e14) continue;
            bars.add(new Bar(date,close.decimalValue()));
        }
        if(bars.isEmpty()) throw new IOException("No completed closing prices available");
        return bars;
    }
    public List<Story> news(String name,String symbol) throws Exception {
        return news(name,symbol,"INR");
    }
    public List<Story> news(String name,String symbol,String currency) throws Exception {
        String company=companyName(name);
        String query="\""+company+"\" when:7d";
        return parseNews(fetch("https://news.google.com/rss/search?q="+encode(query)+(currency.equals("USD")?"&hl=en-US&gl=US&ceid=US%3Aen":"&hl=en-IN&gl=IN&ceid=IN%3Aen")),name,symbol,Instant.now());
    }
    public List<Story> research(String query,Set<String> terms) throws Exception {
        String q="("+query+") when:7d";
        return parseNews(fetch("https://news.google.com/rss/search?q="+encode(q)+"&hl=en-IN&gl=IN&ceid=IN%3Aen"),
            headline -> terms.stream().anyMatch(term -> Pattern.compile("(?i)(?<![a-z])"+Pattern.quote(term)+"(?![a-z])").matcher(headline).find()),Instant.now());
    }
    static String companyName(String name) {
        return name.replaceAll("(?i)\\s+-\\s+.*$","").replaceAll("(?i)\\s+(inc\\.?|corporation|corp\\.?)$","").replaceAll("(?i)\\s+(limited|ltd\\.?|l)$","").trim();
    }
    public static List<Story> parseNews(byte[] xml,String name,String symbol,Instant now) throws Exception {
        return parseNews(xml,headline -> mentions(headline,name,symbol),now);
    }
    static List<Story> parseNews(byte[] xml,Predicate<String> relevant,Instant now) throws Exception {
        var factory=DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities",false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities",false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD,""); factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA,"");
        var items=factory.newDocumentBuilder().parse(new ByteArrayInputStream(xml)).getElementsByTagName("item");
        List<Story> result=new ArrayList<>(); Set<String> seen=new HashSet<>();
        for(int i=0;i<items.getLength() && result.size()<30;i++) {
            var item=(Element)items.item(i);
            String headline=tag(item,"title"),source=tag(item,"source"),url=tag(item,"link");
            if(!source.isBlank() && headline.endsWith(" - "+source)) headline=headline.substring(0,headline.length()-source.length()-3);
            headline=headline.replaceAll("<[^>]*>","").replaceAll("\\s+"," ").trim();
            if(headline.isBlank() || !relevant.test(headline)) continue;
            Instant date;
            try { date=ZonedDateTime.parse(tag(item,"pubDate"),DateTimeFormatter.RFC_1123_DATE_TIME).toInstant(); }
            catch(Exception ignored) { continue; }
            if(date.isBefore(now.minus(Duration.ofDays(7))) || date.isAfter(now.plusSeconds(300))) continue;
            try { var uri=URI.create(url); if(!"https".equals(uri.getScheme()) || uri.getHost()==null) continue; }
            catch(Exception ignored) { continue; }
            String fingerprint=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(headline.toLowerCase(Locale.ROOT).getBytes(StandardCharsets.UTF_8)));
            if(seen.add(fingerprint)) result.add(new Story(headline,url,source.isBlank()?"Google News":source.substring(0,Math.min(source.length(),200)),date,sentiment(headline),fingerprint));
        }
        return result;
    }
    public static boolean mentions(String headline,String name,String symbol) {
        String h=headline.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+"," ");
        String n=companyName(name).toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+"," ").trim();
        if(n.length()>3 && (" "+h+" ").contains(" "+n+" ")) return true;
        // Short/common tickers are ambiguous outside exchange data.
        return symbol.length()>=4 && !Set.of("IDEA","MORE","RAIN","TECH","GOLD","SILVER").contains(symbol)
            && Pattern.compile("(?i)(?<![a-z0-9])"+Pattern.quote(symbol)+"(?![a-z0-9])").matcher(headline).find();
    }
    public static String sentiment(String headline) {
        String h=headline.toLowerCase(Locale.ROOT);
        if(Pattern.compile("\\b(may|might|could|not|denies|rumou?r|if)\\b|\\?").matcher(h).find()) return "NEUTRAL";
        boolean positive=Pattern.compile("\\b(profit (rises|jumps|surges|grows)|record profit|wins? (an? |the )?(order|contract)|secures? (an? |the )?(order|contract)|approval|profits rise|dividend|earnings beat)\\b").matcher(h).find()
            || Pattern.compile("\\b(sales|exports|orders|revenue|earnings|profits?|demand|output)\\b.{0,35}\\b(rise|rises|rose|jump|jumps|surge|surges|grow|grows|grew|gain|gains|advance|advances|rebound|rebounds)\\b").matcher(h).find();
        boolean negative=Pattern.compile("\\b(profit (falls|drops|declines|slumps)|loss widens|losses widen|fraud|penalty|penalties|default|recall|probe|earnings miss|downgrade|funding pressure|weak demand)\\b").matcher(h).find()
            || Pattern.compile("\\b(sales|exports|orders|revenue|earnings|profits?|demand|output)\\b.{0,35}\\b(fall|falls|fell|drop|drops|slump|slumps|slip|slips|decline|declines|slide|slides|plunge|plunges|weaken|weakens)\\b").matcher(h).find();
        return positive&&negative?"MIXED":positive?"POSITIVE":negative?"NEGATIVE":"NEUTRAL";
    }
    private static String tag(Element element,String tag) { var nodes=element.getElementsByTagName(tag); return nodes.getLength()==0?"":nodes.item(0).getTextContent().trim(); }
    private static String encode(String s) { return URLEncoder.encode(s,StandardCharsets.UTF_8); }
}
