# EO AgriTool
![EOAgriTool](EOAgriTool.gif)
EO AgriTool is a cutting-edge web application designed to empower Egyptian farmers and agricultural businesses to overcome environmental challenges. By leveraging high-resolution Earth observation data and embracing regenerative agriculture practices, the app provides actionable insights for sustainable farming.

## Presentation

Download the project presentation here: [EOAgriTool Presentation (.pptx)](https://github.com/aimtyaem/EOAgriTool/raw/9e8e9bbfe0ff0eef161a98a858f13c1110658477/Documents/EOAgriTool.pptx)

---

## 1. Project Overview

**Purpose:**  
EO AgriTool aims to address critical agricultural challenges by integrating data from diverse sources (satellites, UAVs, and ground sensors) and providing farmers with:
- **Real-time alerts** for weather extremes and crop health issues.
- **Custom reports** that deliver targeted insights to improve farm management.
- **Interactive maps** that visualize complex environmental data for on-the-ground decision-making.

**Target Audience:**  
Egyptian farmers and agricultural stakeholders seeking to enhance sustainability, improve crop yields, and ultimately reduce their environmental footprint.

**Problem Addressed:**  
Agriculture faces multiple adversities—including unpredictable weather, pest infestations, water scarcity, and soil degradation—that directly impact productivity and profitability. EO AgriTool[...]

---

## 2. Key Features

- **Real-Time Alerts:**  
  Receive immediate notifications about extreme weather, pest outbreaks, and water shortages, allowing for proactive interventions.

- **Custom Reports:**  
  Generate in-depth, customizable reports analyzing:
  - Crop health and yield predictions.
  - Water resource management.
  - Environmental impact assessments.

- **Interactive Maps:**  
  Explore high-resolution, multi-layered maps displaying:
  - Soil moisture levels.
  - Vegetation indices.
  - Land use patterns and topographic data.

- **Data Integration:**  
  Seamlessly combines data from:
  - Satellites (e.g., EgSA, NARSS).
  - Aerial platforms (drones, aircraft).
  - Ground-based sensors for localized accuracy.

- **Regenerative Agriculture Insights:**  
  Supports sustainable practices such as:
  - **No-till farming:** Preserving soil structure by minimizing disturbance.
  - **Crop diversification:** Enhancing soil health and biodiversity.
  - **Organic matter recycling:** Utilizing natural compost and residues to enrich soil.
  - **Sustainable grazing management:** Preventing overgrazing while maintaining ground cover.

- **User Authentication & Dashboard:**  
  Secure sign-up/log-in features and a personalized dashboard for managing your profile, viewing alerts, and accessing reports.

---

## 3. Tech Stack

- **Front-End:**  
  - JavaScript for responsive and dynamic user interfaces.
  - GIT for version control.
  - Agentic AI, GPT platform chatbots for CSS / Grok for mockup, modern design.

- **Back-End:**  
  - Node.js with Express.js for building scalable APIs.
  - Integration with external data providers (EO OpenAI, EgSA Portal, & EgSA APIs).

- **Database:**  
  - MongoDB / PostgreSQL for flexible, high-performance data storage.

- **Additional Tools & Libraries:**  
  - Deepseek R1 model / Gemini flash 2.0 experiential thinking for raster data codes and data visualizations.
  - Machine Learning libraries (Agentic AI, AI studios) for predictive analytics.

---

## 4. Installation and Setup

### Prerequisites
- [Python](https://www.python.org)
- [Node.js](https://nodejs.org/en/) (v14 or above)
- [Azure](https://portal.azure.com)
- [Git](https://git-scm.com/)

### Instructions
1. **Clone the Repository:**
   ```bash
   git clone https://github.com/yourusername/EO-AgriTool.git
   cd EO-AgriTool
   ```

2. **Install Dependencies:**


### Nodejs:
## Update System Packages:

```bash
sudo apt update && sudo apt upgrade -y
```


   ```bash
   npm install
   ```

3. **Run the Application Locally:**
   ```bash
   npm start
   ```
   The app will be available at `http://localhost:3000` by default.
   [![Build and deploy Node.js app to Azure Web App - exprec](https://github.com/aimtyaem/EOAgriTool/actions/workflows/github_exprec.yml/badge.svg)](https://github.com/aimtyaem/EOAgriTool/actions/workflows/github_exprec.yml)

### Python:

**Install Required Dependencies:**


```bash
sudo apt install software-properties-common -y
```


**Add Python 3.9 Repository:**

```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
```

## Install Python 3.9:

```bash
sudo apt install python3.9 -y
```

**Verify Installation:**

```bash
python3.9 --version
```

The output should display `Python 3.9.x` (where `x` is the minor version number).

[![Build and deploy Python app to Azure Web App - EOAgriTool](https://github.com/aimtyaem/EOAgriTool/actions/workflows/main_eoagritool.yml/badge.svg)](https://github.com/aimtyaem/EOAgriTool/actions/workflows/main_eoagritool.yml)

For further details and advanced configurations, please refer to the [Python Official Documentation](https://docs.python.org/3.9). 



---

## 5. Interactive Mockup

A mockup design demonstrating key aspects of EO AgriTool’s interface is located in the [`EOAgriTool`](https://aimtyaem.github.io/EOAgriTool/dashboard.html) directory. Here you can view:
- The interactive dashboard.
- Custom report generation pages.
- Dynamic interactive maps with real-time data overlays.

---

## 6. Contribution Guidelines

We welcome contributions to improve EO AgriTool! To contribute:
1. **Fork the Repository:** Create your own fork and work on a feature branch.
2. **Submit Issues:** Report bugs or suggest enhancements by creating new issues.
3. **Pull Requests:** Ensure your code adheres to our coding standards and includes relevant tests. Submit a pull request for review.

For detailed contributing guidelines, please see our [CONTRIBUTING.md](contributing.md) file.

---

## 7. Contact Information

For any questions, feedback, or collaboration inquiries, please contact us:

- **Email:** [support@eoagritool.com](mailto:qimt16@hotmail.com)
- **GitHub Issues:** Use the issues section on our repository to report bugs or feature requests.
- **Social Media:** Follow us on Twitter [@EOAgriTool](https://x.com/aimt) for the latest updates.

---

By integrating Earth observation data with principles of regenerative agriculture, EO AgriTool not only empowers farmers with actionable insights but also paves the way for a more sustainable and[...]

Feel free to explore the repository and get involved!

---

This informative `README.md` file ensures developers, contributors, and end-users have all the necessary information to understand, install, and contribute to EO AgriTool.

## Live data & refresh

The climate, water, and fields views use the Quart backend's live-data endpoints. The backend retrieves forecast data from [Open-Meteo](https://open-meteo.com/) without an API key and attributes the provider in each response.

- `GET /climate_data?region=nile_delta&horizon=72h` returns hourly temperature, rainfall, wind, timestamps, and current values. Supported regions are `nile_delta`, `sahel`, `mediterranean`, and `southeast_asia`; supported horizons are `72h`, `7d`, and `30d`.
- `GET /water_data?region=nile_delta` returns average soil moisture, total reference evapotranspiration (`et0_total_mm`), rainfall, irrigation deficit, and hourly series.
- Responses include `fetched_at`, `source`, `region`, and `stale`. The frontend displays the refresh age separately from user-edit timestamps.

The server keeps a five-minute in-process cache keyed by region and forecast type. A refresh control is available on climate and water pages, and those pages also refresh when their selectors change. Fields refresh their live irrigation metric independently while preserving the complete `localStorage` record under `fieldData`, including uploaded media and each field's `lastUpdated` value. `field.lastUpdated` is the time a user changed a field; `data.fetched_at` is the time external data was retrieved. These values must not be merged.

If Open-Meteo fails after a successful request, the endpoint returns HTTP 200 with `stale: true`, `source: "cache"`, and the last-good data. If no successful data exists, the endpoint returns a stale fallback with `data: null`; the frontend shows an error state and does not replace an existing chart or local field records. Loading controls expose a spinner and `aria-busy` state, while stale and error banners explain what the user is seeing.

