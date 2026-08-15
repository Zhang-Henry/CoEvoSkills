"""End-to-end migration entry point."""
import sys
import os

# Add scripts directory to path
scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scripts_dir)

from migrate_pom import migrate_pom
from migrate_namespaces import migrate_all_namespaces
from migrate_security import migrate_security_config
from migrate_resttemplate import migrate_external_api_service
from migrate_properties import migrate_properties, migrate_test_properties

def run_full_migration(workspace='/workspace'):
    """Run the complete Spring Boot 2.7 → 3.2 migration."""
    print("=== Starting Spring Boot Migration ===")
    print()

    # 1. Migrate pom.xml
    print("[1/5] Migrating pom.xml...")
    migrate_pom(os.path.join(workspace, 'pom.xml'))
    print()

    # 2. Migrate javax → jakarta namespaces
    print("[2/5] Migrating javax → jakarta namespaces...")
    migrate_all_namespaces(os.path.join(workspace, 'src'))
    print()

    # 3. Migrate SecurityConfig
    print("[3/5] Migrating SecurityConfig...")
    migrate_security_config(os.path.join(workspace, 'src/main/java/com/example/userservice/config/SecurityConfig.java'))
    print()

    # 4. Migrate ExternalApiService (RestTemplate → RestClient)
    print("[4/5] Migrating ExternalApiService (RestTemplate → RestClient)...")
    migrate_external_api_service(os.path.join(workspace, 'src/main/java/com/example/userservice/service/ExternalApiService.java'))
    print()

    # 5. Migrate application.properties
    print("[5/5] Migrating application.properties...")
    migrate_properties(os.path.join(workspace, 'src/main/resources/application.properties'))
    migrate_test_properties(os.path.join(workspace, 'src/test/resources/application-test.properties'))
    print()

    print("=== Migration Complete ===")

if __name__ == '__main__':
    workspace = sys.argv[1] if len(sys.argv) > 1 else '/workspace'
    run_full_migration(workspace)
