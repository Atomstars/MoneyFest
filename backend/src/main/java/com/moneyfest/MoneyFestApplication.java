package com.moneyfest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration;

@SpringBootApplication(exclude=UserDetailsServiceAutoConfiguration.class)
public class MoneyFestApplication {
    public static void main(String[] args) throws Exception {
        if (java.util.Arrays.asList(args).contains("--init-local-databases")) {
            Class.forName("org.postgresql.Driver");
            try (var connection=java.sql.DriverManager.getConnection("jdbc:postgresql://127.0.0.1:55432/postgres","moneyfest","")) {
                for (String name:java.util.List.of("moneyfest","moneyfest_test")) {
                    try (var query=connection.prepareStatement("SELECT 1 FROM pg_database WHERE datname=?")) {
                        query.setString(1,name);
                        try (var result=query.executeQuery()) {
                            if (!result.next()) try (var statement=connection.createStatement()) { statement.execute("CREATE DATABASE "+name); }
                        }
                    }
                }
            }
            System.out.println("Local application and test databases are ready.");
            return;
        }
        SpringApplication.run(MoneyFestApplication.class, args);
    }
}
