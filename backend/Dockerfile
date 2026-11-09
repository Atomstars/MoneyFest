FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
RUN groupadd --system moneyfest && useradd --system --gid moneyfest moneyfest
COPY --from=build --chown=moneyfest:moneyfest /build/target/moneyfest-backend-0.1.0.jar app.jar
USER moneyfest
EXPOSE 10000
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/app.jar"]
