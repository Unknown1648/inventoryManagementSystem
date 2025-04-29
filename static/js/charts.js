let chartInstance = null;
        
            async function loadQuantityChart() {
                const res = await fetch('/product_quantity_over_time');
                const data = await res.json();
        
                const labels = Object.values(data)[0]?.dates || [];
        
                const datasets = Object.entries(data).map(([product, info]) => ({
                    label: product,
                    data: info.quantities,
                    fill: false,
                    borderColor: getRandomColor(),
                    tension: 0.3
                }));
        
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
                                text: 'Product Quantities Over Last 7 Days'
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
                                    text: 'Date'
                                }
                            }
                        }
                    }
                });
            }
        
            function resetChart() {
                if (chartInstance) {
                    chartInstance.destroy();
                    chartInstance = null;
                }
            }
        
            function getRandomColor() {
                const r = Math.floor(Math.random() * 200);
                const g = Math.floor(Math.random() * 200);
                const b = Math.floor(Math.random() * 200);
                return `rgba(${r}, ${g}, ${b}, 0.7)`;
            }
        
            loadQuantityChart();