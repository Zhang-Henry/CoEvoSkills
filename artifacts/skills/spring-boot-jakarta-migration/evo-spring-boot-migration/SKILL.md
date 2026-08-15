---
name: evo-spring-boot-migration
description: "Migrate a Spring Boot 2.7/Java 8 microservice to Spring Boot 3.2/Java 21. Handles pom.xml updates, javax-to-jakarta namespace migration, Spring Security 6 component-based config, RestTemplate-to-RestClient migration, Hibernate 6 compatibility, and application properties updates."
---

# Spring Boot 2.7 → 3.2 Migration Skill

## Overview
This skill migrates a Spring Boot 2.7.x / Java 8 microservice to Spring Boot 3.2.x / Java 21.

## Migration Steps
1. **pom.xml**: Update parent to Spring Boot 3.2.5, Java 21, replace jjwt with jjwt-api/impl/jackson 0.12.5, remove javax.xml.bind
2. **Namespaces**: javax.persistence/validation/servlet → jakarta.*
3. **Security**: WebSecurityConfigurerAdapter → SecurityFilterChain bean, EnableGlobalMethodSecurity → EnableMethodSecurity, antMatchers → requestMatchers, authorizeRequests → authorizeHttpRequests, lambda DSL
4. **HTTP Client**: RestTemplate → RestClient
5. **Properties**: Remove explicit Hibernate dialect (Hibernate 6 auto-detects)

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-spring-boot-migration/scripts')
from run_migration import run_full_migration

run_full_migration('/workspace')
```

## Individual Scripts
- `migrate_pom.py` - Updates pom.xml dependencies and versions
- `migrate_namespaces.py` - Replaces javax.* with jakarta.* in all Java files
- `migrate_security.py` - Rewrites SecurityConfig for Spring Security 6
- `migrate_resttemplate.py` - Rewrites ExternalApiService to use RestClient
- `migrate_properties.py` - Updates application.properties for Hibernate 6
- `run_migration.py` - End-to-end entry point that calls all of the above
