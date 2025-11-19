# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system-level dependencies required for the mariadb Python package.
RUN apt-get update && apt-get install -y libmariadb-dev gcc && \
    rm -rf /var/lib/apt/lists/*


# Copy requirements file
COPY requirements.txt ./

# Install the Python dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container.
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# This default is overridden by the 'command' in docker-compose.yaml for each service
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
