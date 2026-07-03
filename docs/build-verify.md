# Build, Smoke-Test, SBOM, and Audit Guide

## 1. Prerequisites

```bash
# JDK 21+
java -version
# openjdk version "21.0.5" 2024-10-15 LTS

# Maven 3.9+
mvn --version
# Apache Maven 3.9.9

# Optional: NVD API key for OWASP Dependency-Check (free from NVD)
export NVD_API_KEY="d2eb91b1-551e-4b6c-b69a-c148e60da3bf"