document.addEventListener("DOMContentLoaded", function() {
    const recommendationsContainer = document.getElementById("recommendationsContainer");
    const detailsContainer = document.getElementById("detailsContainer");

    // Fetch recommendations
    fetch("http://localhost:5000/recommendations")
        .then(response => response.json())
        .then(data => {
            data.forEach((recommendation, index) => {
                const recommendationItem = document.createElement("div");
                recommendationItem.className = "recommendation-item";
                recommendationItem.innerText = recommendation;
                recommendationItem.setAttribute("data-index", index);

                // Add click event to fetch details
                recommendationItem.addEventListener("click", function() {
                    const index = this.getAttribute("data-index");
                    fetchDetails(index);
                });

                recommendationsContainer.appendChild(recommendationItem);
            });
        })
        .catch(error => console.error("Error fetching recommendations:", error));

    function fetchDetails(index) {
        fetch("http://localhost:5000/details", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ index: parseInt(index) })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                detailsContainer.innerText = data.error;
            } else {
                detailsContainer.innerText = `${data.recommendation}\n\n${data.details}`;
            }
        })
        .catch(error => console.error("Error fetching details:", error));
    }
});
