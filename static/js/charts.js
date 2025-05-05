let chartInstance = null;
let windowOffset = 0; // 0 = current 24h, -1 = previous 24h, etc.

async function loadQuantityChart() {
    console.log("Loading chart with offset:", windowOffset);  // Log the offset being used

    const res = await fetch(`/product_quantity_over_time?offset=${windowOffset}`);
    
    if (!res.ok) {
        console.error("Failed to load data:", res.statusText);
        return;
    }

    const data = await res.json();
    console.log("Received Data:", data);  // Log the received data

    if (data.error) {
        console.error(data.error);  // Log if there's an error message from Flask
        return;
    }

    const labels = Object.values(data)[0]?.dates || [];
    const datasets = Object.entries(data).map(([product, info]) => {
        return {
            label: product,
            data: info.quantities,
            fill: false,
            borderColor: getRandomColor(),
            tension: 0.3
        };
    });

    const ctx = document.getElementById('quantityChart').getContext('2d');
    if (chartInstance) chartInstance.destroy();

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: `Product Quantities (${24 * Math.abs(windowOffset)}-${24 * (Math.abs(windowOffset) + 1)} hrs ago)`
                },
                legend: {
                    display: true
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Quantity Remaining'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Date & Time'
                    }
                }
            }
        }
    });

    // Disable the "Next 24hrs" button if we are already at 0 (current time window)
    const nextButton = document.getElementById('nextButton');
    if (windowOffset === 0) {
        nextButton.disabled = true; // Disable the Next button
    } else {
        nextButton.disabled = false; // Enable the Next button
    }
}

function getRandomColor() {
    const r = Math.floor(Math.random() * 200);
    const g = Math.floor(Math.random() * 200);
    const b = Math.floor(Math.random() * 200);
    return `rgba(${r}, ${g}, ${b}, 0.7)`;
}

function resetChart() {
    windowOffset = 0;
    loadQuantityChart();
}

function shiftTimeWindow(direction) {
    windowOffset += direction;
    loadQuantityChart();
}

loadQuantityChart(); // Initial load
