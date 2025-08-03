# --- Stage 1: Base Setup ---
# Use a slim, official Python image to keep the final image size down.
FROM python:3.10-slim

# Set an environment variable to prevent apt-get from prompting for user input.
ENV DEBIAN_FRONTEND=noninteractive

# Set the working directory inside the container.
WORKDIR /app

# --- Stage 2: Install Google Chrome, ChromeDriver, and System Dependencies ---
# We need wget and unzip to download and install ChromeDriver.
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    --no-install-recommends

# Add Google's official repository for Chrome.
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'

# Install Google Chrome.
RUN apt-get update && apt-get install -y \
    google-chrome-stable \
    --no-install-recommends

# Download and install the correct version of ChromeDriver.
# This version matches the stable Chrome version installed above.
RUN CHROME_VERSION=$(google-chrome --version | cut -f 3 -d ' ' | cut -d '.' -f 1-3) && \
    CHROMEDRIVER_VERSION=$(wget -qO- "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | jq -r ".channels.Stable.downloads.chromedriver[] | select(.platform==\"linux64\") | .url") && \
    wget -O /tmp/chromedriver.zip ${CHROMEDRIVER_VERSION} && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin/ && \
    mv /usr/local/bin/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm /tmp/chromedriver.zip

# --- Stage 3: Install Python Dependencies ---
# Copy the requirements file into the container.
COPY requirements.txt .

# Install the Python libraries.
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 4: Copy Application and Run ---
# Copy the rest of your application's code into the container.
COPY . .

# Tell Docker that the container will listen on this port at runtime.
# Render provides the port number via the PORT environment variable.
EXPOSE 10000

# The command to run your application using Gunicorn.
# This is the standard for running Flask apps in production.
# It binds to all network interfaces on the port Render provides.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "main:app"]
