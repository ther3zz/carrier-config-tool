# DID Provisioning and Management Platform

## Table of Contents
1. [Overview](#overview)
2. [Features](#features)
    - [Web Interface (Flask)](#web-interface-flask)
    - [Provisioning API (FastAPI)](#provisioning-api-fastapi)
3. [Architecture](#architecture)
4. [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Installation](#installation)
5. [Configuration](#configuration-environment-variables)
6. [Application Usage](#application-usage)
    - [Running the Services](#running-the-services)
    - [Web UI First Steps](#web-ui-first-steps)
    - [Using the Provisioning API](#using-the-provisioning-api)
7. [API Documentation](#api-documentation)
8. [Security](#security)
9. [Logging](#logging)

## Overview

This project provides a robust platform for managing telecommunication services, specifically focusing on provisioning and configuring Direct Inward Dialing (DID) numbers through the Vonage API (more providers are planned). It is composed of two primary components:

1.  **A Flask-based Web Interface**: A comprehensive user interface for manual, detailed management of credentials, Vonage subaccounts, DIDs, and SIP trunks.
2.  **A FastAPI-based REST API**: A secure, high-performance API designed for automated, programmatic provisioning and management of DIDs.

The application uses a MariaDB database for persistent and secure storage of credentials and settings, and is fully containerized with Docker for easy deployment and scalability.

## Features

### Web Interface (Flask)

-   **Secure Credential Management**: Securely add, update, delete, and import API credentials. All secrets are encrypted at rest using a master key.
-   **Subaccount Management**: Create, list, and update Vonage subaccounts directly from the UI.
-   **DID Operations**:
    -   **Search & Buy**: Search for available DIDs by country, pattern, and features.
    -   **Bulk Purchase**: Purchase DIDs in bulk by providing a list of NPAs (US/CA).
    -   **Modify & Release**: Perform bulk updates or releases on lists of existing DIDs.
-   **SIP Trunk (PSIP) Configuration**: Create and manage SIP trunking domains.
-   **Application Settings**: Configure application behavior, API concurrency, and webhook notifications through a settings panel.
-   **Log Management**: Download or clear server-side logs.

### Provisioning API (FastAPI)

-   **Secure Endpoints**: All endpoints are protected by an API key and an optional IP address whitelist.
-   **DID Lifecycle Management**:
    -   `/provision-did`: Search for and purchase a new DID for a specific group.
    -   `/update-did`: Update the voice callback configuration for an existing DID.
    -   `/release-did`: Release a DID from a group's account.
-   **Batch Operations**:
    -   `/provision-dids-batch`: Provision multiple DIDs from a list of NPAs in a single request.
    -   `/update-dids-batch`: Update the configuration for a large number of DIDs concurrently.
    -   `/release-dids-batch`: Release multiple DIDs in a single request.
-   **Subaccount Automation**: Automatically create a new Vonage subaccount during provisioning if one does not already exist for the specified `groupid`.
-   **Configuration Management**: Endpoints to manage default callback settings for a group.
-   **Webhook Notifications**: Automatically sends webhook notifications for key events like DID provisioning, releases, and subaccount creation.

## Architecture

The platform is built on a microservices-style architecture, with two distinct services running in Docker containers:

-   **`flask_app`**: The frontend service that serves the web UI on port `5000`.
-   **`fastapi_app`**: The backend API service that provides RESTful endpoints for automation on port `8000`.
-   **`mariadb`**: (Not included in the provided `docker-compose.yaml` but required) A MariaDB database instance for storing all application data, including encrypted credentials and settings.
-   **Docker & Docker Compose**: Used for containerization and orchestration of the services, ensuring a consistent and reproducible environment.

## Getting Started

### Prerequisites

-   Docker
-   Docker Compose
-.  A running MariaDB instance accessible from the Docker environment.

### Installation

1.  **Clone the Repository**
    ```sh
    git clone <your-repository-url>
    cd <repository-directory>
    ```

2.  **Generate Encryption Salt**
    A persistent, secret salt is required for deriving encryption keys. Generate a secure salt and save it for the next step. **Do not lose this salt**, as it is essential for decrypting your data.

    ```sh
    python -c "import os; print(os.urandom(16).hex())"
    ```

3.  **Create the Environment File**
    Copy the `.env.example` file to `.env` and populate it with your configuration details.

    ```sh
    cp .env.example .env
    ```

    **Example `.env` file:**
    ```ini
    # --- Database Configuration ---
    DB_HOST=your_database_host
    DB_PORT=3306
    DB_USER=your_database_user
    DB_PASSWORD=your_database_password
    DB_NAME=your_database_name

    # --- Application Settings ---
    # Storage mode for credentials. 'db' is required for the FastAPI service.
    CREDENTIAL_STORAGE_MODE=db
    # Path to the directory where logs will be stored on the host machine.
    LOGS_DIRECTORY=./logs

    # --- Security & Encryption (CRITICAL) ---
    # The persistent salt generated in the previous step.
    ENCRYPTION_SALT=your_generated_32_character_hex_salt
    # The master key used by the FastAPI service for automatic decryption of credentials.
    MASTER_KEY=your_strong_and_secret_master_key
    # The API key required to access the FastAPI endpoints.
    FASTAPI_PROVISIONING_KEY=your_secure_fastapi_access_key

    # --- API Configuration (Optional but Recommended) ---
    # Comma-separated list of IPs allowed to access the FastAPI. Leave empty to allow all.
    FASTAPI_IP_WHITELIST=192.168.1.100,10.0.0.5
    # The name of the primary Vonage account credential (as saved in the UI) to be used for creating subaccounts.
    VONAGE_PRIMARY_ACCOUNT_NAME=Vonage-Primary-Account
    # Comma-separated list of trusted proxy IPs if the app is behind a reverse proxy.
    TRUSTED_PROXY_IPS=127.0.0.1,::1
    ```

## Configuration (Environment Variables)

The following table lists all the environment variables used to configure the application.

| Variable                      | Required | Description                                                                                                                              |
| ----------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `DB_HOST`                     | **Yes**  | The hostname or IP address of the MariaDB server.                                                                                        |
| `DB_PORT`                     | **Yes**  | The port number for the MariaDB server.                                                                                                  |
| `DB_USER`                     | **Yes**  | The username for connecting to the database.                                                                                             |
| `DB_PASSWORD`                 | **Yes**  | The password for the database user.                                                                                                      |
| `DB_NAME`                     | **Yes**  | The name of the database to use.                                                                                                         |
| `CREDENTIAL_STORAGE_MODE`     | **Yes**  | Must be set to `db`. The 'file' mode is for legacy support and is incompatible with the FastAPI service.                                       |
| `LOGS_DIRECTORY`              | **Yes**  | The path on the host machine where log files will be mounted and stored.                                                                 |
| `ENCRYPTION_SALT`             | **Yes**  | A persistent, 32-character hex string used for key derivation. **Critical for data recovery.**                                           |
| `MASTER_KEY`                  | **Yes**  | The master key used by the FastAPI service to decrypt credentials from the database. Must match the key used in the UI to save credentials. |
| `FASTAPI_PROVISIONING_KEY`    | **Yes**  | The secret API key that clients must provide in the `X-API-Key` header to access the FastAPI endpoints.                                    |
| `FASTAPI_IP_WHITELIST`        | No       | A comma-separated list of IP addresses that are permitted to access the FastAPI. If not set, access is not restricted by IP.              |
| `VONAGE_PRIMARY_ACCOUNT_NAME` | No       | The "Friendly Name" of the main Vonage account credential stored in the database. Required for the auto-create subaccount feature.         |
| `TRUSTED_PROXY_IPS`           | No       | A comma-separated list of trusted proxy server IPs. Set this if the application is behind a reverse proxy to correctly identify client IPs.  |

## Application Usage

### Running the Services

Use Docker Compose to build and run the services. You can run one or both services by specifying their profiles.

-   **Run both the UI and API services:**
    ```sh
    docker-compose --profile ui --profile api up --build -d
    ```

-   **Run only the Web UI:**
    ```sh
    docker-compose --profile ui up --build -d
    ```

-   **Run only the Provisioning API:**
    ```sh
    docker-compose --profile api up --build -d
    ```

-   **To stop the services:**
    ```sh
    docker-compose down
    ```

### Web UI First Steps

1.  Access the web interface by navigating to `http://localhost:5000`.
2.  Go to the **Credential Management** section.
3.  Enter a **Session Master Key**. This key is used within your browser session to encrypt/decrypt secrets before they are sent to the server. For the FastAPI service to function correctly, this key must match the `MASTER_KEY` environment variable.
4.  Click **Set & Load**.
5.  You can now add your Vonage API credentials, which will be encrypted with this key and stored in the database.

### Using the Provisioning API

-   **Base URL**: `http://localhost:8000`
-   **Authentication**: All requests to the API must include the `X-API-Key` header with the value of your `FASTAPI_PROVISIONING_KEY`.
-   **IP Whitelisting**: If `FASTAPI_IP_WHITELIST` is configured, requests will only be accepted from the specified IP addresses.

## API Documentation

The FastAPI service provides automatically generated, interactive API documentation. Once the API is running, you can access it at:

-   **Swagger UI**: `http://localhost:8000/docs`
-   **ReDoc**: `http://localhost:8000/redoc`

The main endpoints include:

| Method | Endpoint                    | Description                                                              |
| ------ | --------------------------- | ------------------------------------------------------------------------ |
| `POST` | `/provision-did`            | Provisions a single DID from a specified NPA.                            |
| `POST` | `/release-did`              | Releases a single DID.                                                   |
| `POST` | `/update-did`               | Updates the configuration of a single DID.                               |
| `POST` | `/provision-dids-batch`     | Provisions multiple DIDs from a list of NPAs.                            |
| `POST` | `/release-dids-batch`       | Releases a list of DIDs.                                                 |
| `POST` | `/update-dids-batch`        | Updates the configuration for a list of DIDs.                            |
| `POST` | `/update-group-defaults`    | Sets the default voice callback settings for a `groupid`.                |

## Security

-   **Credential Encryption**: All API secrets are encrypted using Fernet (AES-128-CBC) with a key derived via PBKDF2HMAC-SHA256 from your Master Key and the persistent Salt.
-   **Master Key**: The Master Key is the primary secret for data access. It is required in the browser session for manual management and as an environment variable for the automated API.
-   **API Key Protection**: The FastAPI is protected from unauthorized access via a mandatory API key.
-   **IP Whitelisting**: An additional layer of security can be enabled to restrict API access to known IP addresses.
-   Note: AVOID EXPOSING THE FLASKUI INSTANCE TO THE INTERNET.

## Logging

The application generates several log files in the directory specified by `LOGS_DIRECTORY`:

-   `system.log`: General application events, startup messages, and incoming API request summaries.
-   `notifications.log`: Detailed logs of outgoing webhook notification attempts, including payloads and responses.
-   `<account_id>.log`: For each Vonage account used, a separate log file is created containing detailed, obfuscated request/response logs for all API calls made to Vonage using that account's credentials.
