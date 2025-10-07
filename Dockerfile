# --- START OF FILE Dockerfile ---

# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# --- START: MODIFICATION ---
# Install system-level dependencies required for the mariadb Python package.
# libmariadb-dev: Provides the MariaDB C Connector, headers, and the 'mariadb_config' utility.
# gcc: The GNU C Compiler, which is often required to build Python packages that have C extensions.
# We also update package lists and clean up the cache to keep the image size down.
RUN apt-get update && apt-get install -y libmariadb-dev gcc && \
    rm -rf /var/lib/apt/lists/*
# --- END: MODIFICATION ---

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# This will now succeed because the underlying system dependency is present.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable (optional, good practice)
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Run app.py when the container launches
# This default is overridden by the 'command' in docker-compose.yaml for each service
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]

# --- END OF FILE Dockerfile ---
