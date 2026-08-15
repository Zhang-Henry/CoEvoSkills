"""Migrate pom.xml from Spring Boot 2.7/Java 8 to Spring Boot 3.2/Java 21."""
import re

def migrate_pom(pom_path):
    with open(pom_path, 'r') as f:
        content = f.read()

    # 1. Update Spring Boot parent version to 3.2.x
    content = re.sub(
        r'(<artifactId>spring-boot-starter-parent</artifactId>\s*<version>)2\.7\.[^<]+(</version>)',
        r'\g<1>3.2.5\2',
        content
    )

    # 2. Update Java version from 1.8 to 21
    content = re.sub(
        r'(<java\.version>)[^<]+(</java\.version>)',
        r'\g<1>21\2',
        content
    )

    # 3. Replace old jjwt single dependency with new jjwt-api, jjwt-impl, jjwt-jackson
    old_jjwt = r'''\s*<dependency>\s*<groupId>io\.jsonwebtoken</groupId>\s*<artifactId>jjwt</artifactId>\s*<version>[^<]+</version>\s*</dependency>'''
    new_jjwt = """
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-api</artifactId>
            <version>0.12.5</version>
        </dependency>
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-impl</artifactId>
            <version>0.12.5</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-jackson</artifactId>
            <version>0.12.5</version>
            <scope>runtime</scope>
        </dependency>"""
    content = re.sub(old_jjwt, new_jjwt, content)

    # 4. Remove javax.xml.bind:jaxb-api dependency (not needed with Java 21 + new jjwt)
    content = re.sub(
        r'\s*<!-- Java 8 compatibility for JAXB \(needed for JWT\) -->\s*'
        r'<dependency>\s*<groupId>javax\.xml\.bind</groupId>\s*'
        r'<artifactId>jaxb-api</artifactId>\s*<version>[^<]+</version>\s*</dependency>',
        '',
        content
    )

    with open(pom_path, 'w') as f:
        f.write(content)
    print(f"Migrated pom.xml at {pom_path}")

if __name__ == '__main__':
    import sys
    migrate_pom(sys.argv[1] if len(sys.argv) > 1 else '/workspace/pom.xml')
