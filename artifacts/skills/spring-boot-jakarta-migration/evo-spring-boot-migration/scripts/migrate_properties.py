"""Migrate application.properties for Spring Boot 3.2 / Hibernate 6 compatibility."""

def migrate_properties(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Hibernate 6 auto-detects dialect, remove explicit H2Dialect
    # or update to the new class name
    content = content.replace(
        'spring.jpa.database-platform=org.hibernate.dialect.H2Dialect',
        '# Hibernate 6 auto-detects dialect'
    )

    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Migrated properties at {filepath}")

def migrate_test_properties(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    content = content.replace(
        'spring.jpa.database-platform=org.hibernate.dialect.H2Dialect',
        '# Hibernate 6 auto-detects dialect'
    )

    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Migrated test properties at {filepath}")

if __name__ == '__main__':
    migrate_properties('/workspace/src/main/resources/application.properties')
    migrate_test_properties('/workspace/src/test/resources/application-test.properties')
