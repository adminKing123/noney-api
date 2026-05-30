# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the requirements file into the container
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Expose the port that the application will listen on
# Cloud Run typically expects services to listen on port 8080
ENV PORT 8080
EXPOSE 8080

# Add your environment variables here as requested
ENV CDN_URL=https://noney-api-an60.onrender.com
ENV CRYPTO_NONCE_SIZE=12
ENV CRYPTO_SALT=my-static-salt-1234
ENV CRYPTO_SECRET_KEY=super-secret-password
ENV CRYPTO_SEPARATOR=|
ENV DEBUG=true
ENV ELEVENLABS_API_KEY=sk_9417235ed165bf113091c8bc5a762d85aad4d375f4047192
ENV ELEVENLABS_VOICE_ID=TX3LPaxmHKxFdv7VOQHJ
ENV FIREBASE_CREDENTIALS='{"type": "service_account","project_id": "aura-hypen-dev","private_key_id": "512c933672ff5015139e86c9ff7a7a97d7adc088","private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC08fwE0KpuaWNt\nhtVkqH6M8nAey4RsmOJsnhw8A85dPZkLDYwHLb6IqbS2YBSktjdKdOy1ZiF/4NH6\nsPWFJCzKI8dYGrAev9VncCs5nFxen1cEDhEIvfaLnYZKR9+jHVC2W34srbqwNsX4\n1kFwNX1Kix1Mg+STJoo6SwW9OlghB/sxTvOZZI0ZetdtWVrvb9KODVbD7X8+kff1\n/FbHV2q/NKtQtjCo32R4ZKHd9hOU6CWb3Hm2xGMDtU4IQ2wCieEdIbYVmLtDAJo/\nh84pGSoBYZ6DBhS7K4wQqcn6tSL4J/p7QWIhpYeRvfFrsZpQLdzY++4Oosbt7HAp\nfU91DhZ3AgMBAAECggEAO5uZ56Yr9vp92Cd6ZdIB+oGlQOfPhIzqzlhZucWRNnMj\n1xnL3tOJeHDbiNbnBgnG9h7Fmc5+y6cu1TR1dTphDOgzc8k66q5MaWpwuuZRIZTB\nMCNIJkaaEQ1AH3lE6XGvVJuYWbSTkxhAKITAguwEDcn9SWcLphQkpiZvyhIN1TdC\nyAQhOGmeuHj+TP1WmPzbMlevP+lUlj7OdyY/YX+Adj3XXoCP4sP6Zrx0OvCdLf8+\nmk4QnDzipQcHj8+gS9bFVjba8SnMl4y84qDhwz5PZf9ZmNePOC+iP9ov0bWDiTLu\nsbahHssXtKEy7xV3WV+iNCRAftt9Cnlwx/Hk/To7sQKBgQDvI3F/T/OIRBmKJuCN\nz1A+Q0HkcgFXGzSasGrb3qIH/MhKqCxF/tAaiAnn+4Hv9skUiGUlDqyd4Dna8fZT\nAjnBxlWgqhng0wq2Brm9X35CyjLldiCfdnE0GT+Xr9+SkWPeA1r4l1Fbcy5c0K4Y\n2a+zAq0DLQJ2pLkpxLc8QDp5pwKBgQDBtCCvIr78r60fRJc+onNyLOo4zzcMrM06\nAfozRjUNIHZm4SjgEM043ge5I4k5+tS98phHME6pDgwqLrU0zUPgmb+7a53+iKHe\ng5f7+dXHzphrp0fXCZuJzd9XfCbsFP2J9bkqYznND2brgzd17WOsL0VDhxBZ/GSO\n4W/LOqt2sQKBgQDnw5YQKVCBVF7cQemIBtBiR5To7oTWAwvsj+ZAyXiH/TmxAWRH\nQjo2PHo9VsgL5UXknHxKefpZ2CK6S57LvHB1mN8MI0+JUYAkAkipfI9F8+l38hCT\n+5qjP4UeYdlwl3AOj3nvS9gRpYPdeHICq5dZCtLbLRgiHGtIS9q6jhUeKQKBgDcw\nzJM6EjLLF0eucm2NOdmRRJc1K1k4Ly1U/OX5HgqEclfz1YKqJt8KHCc7IdFcT5tj\ncNHvyKnQb9ThBA5sYeevxvpuulCYu4477mUEFU5d5f3eZtC1UxTbjMRPgoOHo4nY\nco7KQODVf5yhAX9fSSP5QAHyjM0m5bv0Lbc5GzuxAoGBAN0KepQ2WcrmKQLvuFWe\ndR8nnnZXUmlofhBwGOIeoApYaPaLkpMQThlLsJj9e0m12h0R7c/bc5oxeXISUJGX\nPwiFwNmOvR4m9trRYN/3ZYghdxprSyj6RSGGHUyrs1EF4GsTXTElfV8b27kJkwYR\nMomcerLH1g+jiQQiCwgORyHS\n-----END PRIVATE KEY-----\n","client_email": "firebase-adminsdk-fbsvc@aura-hypen-dev.iam.gserviceaccount.com","client_id": "107862229946251697971","auth_uri": "https://accounts.google.com/o/oauth2/auth","token_uri": "https://oauth2.googleapis.com/token","auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40aura-hypen-dev.iam.gserviceaccount.com","universe_domain": "googleapis.com"}'
ENV GITHUB1_BRANCH_NAME=main
ENV GITHUB1_REPO_NAME=dummy-src
ENV GITHUB1_TOKEN=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
ENV GITHUB1_USERNAME=experimental-core
ENV GOOGLE_API_KEY=AIzaSyDyBrmnaq33cVFVbG6l8Y_XsoGL0EawoWk
ENV HOST=https://noney-api-an60.onrender.com

# Run the Flask application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
