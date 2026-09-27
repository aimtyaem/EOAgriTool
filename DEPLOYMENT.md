# EOAgriTool - Deployment & Performance Testing Guide

## Overview

This guide provides step-by-step instructions to deploy EOAgriTool and conduct performance testing across multiple platforms.

---

## Table of Contents

1. [Local Development Setup](#local-development-setup)
2. [Docker Deployment](#docker-deployment)
3. [Cloud Deployment Options](#cloud-deployment-options)
4. [Performance Testing](#performance-testing)
5. [Monitoring & Metrics](#monitoring--metrics)

---

## Local Development Setup

### Prerequisites

- **Python 3.9+** (3.12 recommended)
- **Node.js 14+** (for frontend components)
- **Git**
- **pip** or **conda** (for Python package management)

### Installation Steps

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/aimtyaem/EOAgriTool.git
   cd EOAgriTool
   ```

2. **Create a Python Virtual Environment:**
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Python Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration (API keys, database URLs, etc.)
   ```

5. **Run the Application Locally:**
   ```bash
   python app.py
   ```
   
   The app will be available at `http://localhost:8000`

6. **(Optional) Run with Development Server:**
   ```bash
   hypercorn app:app --bind 0.0.0.0:8000 --reload
   ```

---

## Docker Deployment

### Building the Docker Image

```bash
# Build the image
docker build -t eoagritool:latest .

# Verify the build
docker images | grep eoagritool
```

### Running the Container Locally

```bash
# Run with default settings
docker run -p 8000:8000 \
  --env-file .env \
  eoagritool:latest

# Run with custom port mapping
docker run -p 9000:8000 \
  --env-file .env \
  eoagritool:latest

# Run in detached mode
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name eoagritool-app \
  eoagritool:latest
```

### Verify Container is Running

```bash
# Check logs
docker logs eoagritool-app

# View running containers
docker ps

# Access the app
curl http://localhost:8000
```

### Stop and Clean Up

```bash
# Stop the container
docker stop eoagritool-app

# Remove the container
docker rm eoagritool-app

# Remove the image
docker rmi eoagritool:latest
```

---

## Cloud Deployment Options

### Option 1: Azure Web App (Recommended)

Based on your `azure-pipelines.yml` configuration:

1. **Create an Azure Web App:**
   ```bash
   az webapp create \
     --resource-group <resource-group> \
     --plan <app-service-plan> \
     --name eoagritool \
     --runtime "PYTHON|3.12"
   ```

2. **Configure Environment Variables:**
   ```bash
   az webapp config appsettings set \
     --resource-group <resource-group> \
     --name eoagritool \
     --settings LOG_LEVEL=INFO FLASK_DEBUG=false
   ```

3. **Deploy via GitHub Actions:**
   - Push to your main branch
   - GitHub Actions will automatically deploy via the `main_eoagritool.yml` workflow

4. **Monitor Deployment:**
   ```bash
   az webapp log tail --resource-group <resource-group> --name eoagritool
   ```

### Option 2: AWS Elastic Beanstalk

1. **Install EB CLI:**
   ```bash
   pip install awseb-cli
   ```

2. **Initialize Elastic Beanstalk:**
   ```bash
   eb init -p python-3.12 eoagritool
   eb create eoagritool-env
   ```

3. **Deploy:**
   ```bash
   eb deploy
   ```

4. **Monitor:**
   ```bash
   eb status
   eb logs
   ```

### Option 3: Heroku (Legacy)

```bash
# Install Heroku CLI
# See: https://devcenter.heroku.com/articles/heroku-cli

# Login to Heroku
heroku login

# Create an app
heroku create eoagritool

# Deploy
git push heroku main

# View logs
heroku logs --tail
```

### Option 4: Docker Container Registry (ACR/Docker Hub)

1. **Push to Docker Hub:**
   ```bash
   docker login
   docker tag eoagritool:latest yourusername/eoagritool:latest
   docker push yourusername/eoagritool:latest
   ```

2. **Deploy to Kubernetes (if available):**
   ```bash
   kubectl create deployment eoagritool --image=yourusername/eoagritool:latest
   kubectl expose deployment eoagritool --type=LoadBalancer --port=80 --target-port=8000
   ```

---

## Performance Testing

### 1. Load Testing with Locust

Install Locust:
```bash
pip install locust
```

Create `locustfile.py`:
```python
from locust import HttpUser, task, between

class EOAgriToolUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def load_dashboard(self):
        self.client.get("/")
    
    @task(2)
    def load_reports(self):
        self.client.get("/reports.html")
    
    @task
    def load_water_data(self):
        self.client.get("/water.html")
```

Run the test:
```bash
locust -f locustfile.py --host=http://localhost:8000 -u 100 -r 10 --run-time 1m
```

### 2. Apache Bench (Simple HTTP Benchmarking)

```bash
# Install Apache Bench
sudo apt install apache2-utils

# Run benchmark
ab -n 1000 -c 50 http://localhost:8000/

# Output includes: requests/sec, time per request, failed requests
```

### 3. Artillery.io (Advanced Load Testing)

Install:
```bash
npm install -g artillery
```

Create `load-test.yml`:
```yaml
config:
  target: "http://localhost:8000"
  phases:
    - duration: 60
      arrivalRate: 10
    - duration: 120
      arrivalRate: 20
    - duration: 60
      arrivalRate: 50

scenarios:
  - name: "User Journey"
    flow:
      - get:
          url: "/"
      - get:
          url: "/dashboard.html"
      - get:
          url: "/reports.html"
```

Run:
```bash
artillery run load-test.yml
```

### 4. Python Requests Benchmark

```python
import requests
import time
from concurrent.futures import ThreadPoolExecutor

def test_endpoint(url, iterations=100):
    times = []
    for _ in range(iterations):
        start = time.time()
        response = requests.get(url)
        elapsed = time.time() - start
        times.append(elapsed)
    
    return {
        "avg_time": sum(times) / len(times),
        "min_time": min(times),
        "max_time": max(times),
        "status_codes": response.status_code
    }

if __name__ == "__main__":
    base_url = "http://localhost:8000"
    endpoints = ["/", "/dashboard.html", "/reports.html"]
    
    for endpoint in endpoints:
        results = test_endpoint(f"{base_url}{endpoint}")
        print(f"\n{endpoint}:")
        print(f"  Average: {results['avg_time']:.4f}s")
        print(f"  Min: {results['min_time']:.4f}s")
        print(f"  Max: {results['max_time']:.4f}s")
```

---

## Monitoring & Metrics

### Key Performance Indicators (KPIs) to Track

1. **Response Time:** Avg, P50, P95, P99 latency
2. **Throughput:** Requests per second (RPS)
3. **Error Rate:** 4xx, 5xx errors percentage
4. **CPU Usage:** % utilization
5. **Memory Usage:** RAM consumption
6. **Disk I/O:** Read/write rates

### Azure Monitoring

```bash
# View metrics in Azure Portal
az monitor metrics list \
  --resource-group <resource-group> \
  --resource-type "Microsoft.Web/sites" \
  --resource-name eoagritool
```

### Docker Container Monitoring

```bash
# Monitor CPU and memory
docker stats eoagritool-app

# Inspect container details
docker inspect eoagritool-app
```

### Application Logging Configuration

Set logging level via environment variable:
```bash
export LOG_LEVEL=DEBUG  # Or INFO, WARNING, ERROR
```

Log levels: DEBUG < INFO < WARNING < ERROR < CRITICAL

### Profiling with Python cProfile

Add to your application startup:
```python
import cProfile
import pstats
from io import StringIO

pr = cProfile.Profile()
pr.enable()

# Your application code here

pr.disable()
s = StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
ps.print_stats(10)
print(s.getvalue())
```

---

## Performance Optimization Tips

1. **Use Caching:**
   - Cache static files (HTML, CSS, JS)
   - Implement Redis for session caching

2. **Database Optimization:**
   - Use connection pooling
   - Add indexes on frequently queried columns
   - Optimize queries to avoid N+1 problems

3. **API Optimization:**
   - Implement pagination for large datasets
   - Use compression (gzip) for responses
   - Add rate limiting to prevent abuse

4. **Worker Configuration:**
   - Adjust `--workers` in Procfile based on CPU cores
   - Monitor worker utilization
   - Set appropriate timeouts

5. **Async Operations:**
   - Use Quart's async capabilities for I/O-bound operations
   - Consider task queues (Celery) for long-running tasks

---

## Troubleshooting

### Common Issues

**Issue:** Port already in use
```bash
# Find process on port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>
```

**Issue:** Module not found errors
```bash
# Reinstall dependencies
pip install --force-reinstall -r requirements.txt
```

**Issue:** Out of memory
```bash
# Increase Docker memory limit
docker run -m 2g eoagritool:latest
```

**Issue:** High response times
- Check CPU and memory usage
- Review application logs for errors
- Increase number of workers
- Optimize database queries

---

## Next Steps

1. ✅ Deploy the application to your chosen platform
2. ✅ Run performance tests with load testing tools
3. ✅ Monitor metrics and identify bottlenecks
4. ✅ Optimize based on test results
5. ✅ Set up continuous monitoring in production

---

## Additional Resources

- [Quart Documentation](https://quart.palletsprojects.com/)
- [Hypercorn Documentation](https://hypercorn.readthedocs.io/)
- [Azure Web App Documentation](https://docs.microsoft.com/en-us/azure/app-service/)
- [Docker Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Performance Testing Best Practices](https://www.loadimpact.com/guides/)

---

**Last Updated:** 2026-09-27
**Author:** EOAgriTool Team
