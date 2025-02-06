document.addEventListener('DOMContentLoaded', function() {
    function fetchData(url, elementId, dataKey, displayType = 'list') {
        fetch(url)
            .then(response => response.json())
            .then(data => {
                const element = document.getElementById(elementId);
                if (!element) return;

                if (displayType === 'list') {
                    element.innerHTML = '';
                    
                    if (url.includes('watchlist')) {
                        // Handle sector watchlists
                        const sectorWatchlists = data.watchlist[0].sector_watchlists;
                        Object.entries(sectorWatchlists).forEach(([sector, stocks]) => {
                            const sectorDiv = document.createElement('div');
                            sectorDiv.className = 'sector-group';
                            sectorDiv.innerHTML = `
                                <h3 class="sector-title">${sector}</h3>
                                <div class="sector-stocks">
                                    ${stocks.map(symbol => `
                                        <div class="stock-item">
                                            <span class="symbol">${symbol}</span>
                                            <div class="price flip-board" id="price-${symbol}"></div>
                                            <div class="change flip-board" id="change-${symbol}"></div>
                                        </div>
                                    `).join('')}
                                </div>
                            `;
                            element.appendChild(sectorDiv);
                            
                            // Add mock prices for each stock
                            stocks.forEach(symbol => {
                                const mockPrice = (Math.random() * 1000).toFixed(2);
                                const mockChange = (Math.random() * 10 - 5).toFixed(2);
                                updateFlipBoard(`price-${symbol}`, mockPrice);
                                updateFlipBoard(`change-${symbol}`, mockChange, parseFloat(mockChange) >= 0);
                            });
                        });
                    } else if (url.includes('trades')) {
                        // Handle trades display (compact version)
                        const trades = data.trades;
                        trades.slice(0, 10).forEach(trade => { // Show only last 10 trades
                            const tradeItem = document.createElement('div');
                            tradeItem.className = 'trade-item';
                            tradeItem.innerHTML = `
                                <div class="trade-header">
                                    <span class="trade-symbol">${trade.ticker}</span>
                                    <span class="trade-action ${trade.action}">${trade.action}</span>
                                </div>
                                <div class="trade-details">
                                    <span>${trade.shares} @ $${trade.price.toFixed(2)}</span>
                                    <span class="trade-amount">$${trade.amount.toFixed(2)}</span>
                                </div>
                            `;
                            element.appendChild(tradeItem);
                        });
                    }
                } else if (displayType === 'flip-board') {
                    if (url.includes('summary')) {
                        const summary = data.summary;
                        // Display portfolio holdings
                        const portfolioDiv = document.createElement('div');
                        portfolioDiv.className = 'portfolio-summary';
                        portfolioDiv.innerHTML = `
                            <div class="balance-display">
                                <h4>Balance</h4>
                                <div class="flip-board" id="balance-board">
                                    ${summary.balance.toFixed(2)}
                                </div>
                            </div>
                            <div class="holdings-list">
                                <h4>Current Holdings</h4>
                                ${Object.entries(summary.portfolio).map(([symbol, shares]) => `
                                    <div class="holding-item">
                                        <span class="holding-symbol">${symbol}</span>
                                        <span class="holding-shares">${shares}</span>
                                    </div>
                                `).join('')}
                            </div>
                        `;
                        element.innerHTML = '';
                        element.appendChild(portfolioDiv);
                        updateFlipBoard('balance-board', summary.balance.toFixed(2));
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
                const element = document.getElementById(elementId);
                if (element) element.textContent = "Error loading data.";
            });
    }

    function updateFlipBoard(elementId, value, isPositive = true) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Flip board element not found: ${elementId}`);
            return;
        }

        element.innerHTML = ''; // Clear existing digits
        const digits = value.toString().split('');
        
        if (isPositive !== undefined) {
            element.classList.remove('positive', 'negative');
            element.classList.add(isPositive ? 'positive' : 'negative');
        }

        digits.forEach(digit => {
            const digitSpan = document.createElement('span');
            digitSpan.className = 'digit';
            digitSpan.textContent = digit;
            element.appendChild(digitSpan);
        });
    }

    // Initial data fetch
    fetchData('http://localhost:5000/watchlist', 'watchlist-display', 'watchlist', 'list');
    fetchData('http://localhost:5000/trades', 'trades-display', 'trades', 'list');
    fetchData('http://localhost:5000/summary', 'summary-display', 'summary', 'flip-board');

    // Refresh data every 30 seconds
    setInterval(() => {
        fetchData('http://localhost:5000/watchlist', 'watchlist-display', 'watchlist', 'list');
        fetchData('http://localhost:5000/trades', 'trades-display', 'trades', 'list');
        fetchData('http://localhost:5000/summary', 'summary-display', 'summary', 'flip-board');
    }, 30000);
}); 