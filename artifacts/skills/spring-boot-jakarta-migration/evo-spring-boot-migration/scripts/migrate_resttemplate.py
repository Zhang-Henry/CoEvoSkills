"""Migrate ExternalApiService from RestTemplate to RestClient."""

def get_migrated_external_api_service():
    return '''package com.example.userservice.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.Map;

/**
 * Service for making external API calls using RestClient (Spring Boot 3.x).
 */
@Service
public class ExternalApiService {

    private final RestClient restClient;

    public ExternalApiService(@Value("${external.api.base-url:https://api.example.com}") String baseUrl) {
        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .build();
    }

    /**
     * Verify user email through external service.
     */
    public boolean verifyEmail(String email) {
        try {
            Map response = restClient.get()
                    .uri("/verify-email?email={email}", email)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(Map.class);
            return response != null && Boolean.TRUE.equals(response.get("valid"));
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * Send notification to external service.
     */
    public void sendNotification(String userId, String message) {
        try {
            Map<String, String> request = Map.of(
                    "userId", userId,
                    "message", message
            );
            restClient.post()
                    .uri("/notifications")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .toBodilessEntity();
        } catch (Exception e) {
            // Log and swallow - notification failure should not break the flow
            System.err.println("Failed to send notification: " + e.getMessage());
        }
    }

    /**
     * Fetch user profile from external service.
     */
    public Map<String, Object> fetchExternalProfile(String userId) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> response = restClient.get()
                    .uri("/users/{userId}/profile", userId)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(Map.class);
            return response;
        } catch (Exception e) {
            return null;
        }
    }
}
'''

def migrate_external_api_service(filepath):
    content = get_migrated_external_api_service()
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Migrated ExternalApiService at {filepath}")

if __name__ == '__main__':
    import sys
    migrate_external_api_service(sys.argv[1] if len(sys.argv) > 1 else '/workspace/src/main/java/com/example/userservice/service/ExternalApiService.java')
