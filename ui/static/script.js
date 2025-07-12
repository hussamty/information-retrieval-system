// --- Get references to all the important HTML elements ---
const searchBtn = document.getElementById('search-btn');
const queryInput = document.getElementById('query');
const resultsDiv = document.getElementById('results');
const statusDiv = document.getElementById('status');
const modelSelect = document.getElementById('model_type');
const bm25ParamsDiv = document.getElementById('bm25-params');
const hybridParamsDiv = document.getElementById('hybrid-params');
const hybridWeightSlider = document.getElementById('hybrid_weight');
const weightValueSpan = document.getElementById('weight-value');
const nerToggle = document.getElementById('ner-rerank-toggle');
const clusterToggle = document.getElementById('cluster-rerank-toggle');
const suggestionsBox = document.getElementById('suggestions-box');
const alternativeSuggestionsDiv = document.getElementById('alternative-suggestions');
let suggestionTimeout; // A variable to hold the timeout for suggestion fetching

// --- Add event listeners to interactive elements ---
modelSelect.addEventListener('change', toggleParams); // When the model is changed, show/hide relevant params
hybridWeightSlider.addEventListener('input', () => { weightValueSpan.textContent = hybridWeightSlider.value; }); // Update the weight value display as the slider moves
searchBtn.addEventListener('click', performSearch); // When the search button is clicked, start a search
queryInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') performSearch(); }); // Also search when Enter is pressed in the input box
queryInput.addEventListener('input', handleSuggestionInput); // When the user types, fetch suggestions
// Hide the suggestion box if the user clicks anywhere else on the page
document.addEventListener('click', (e) => {
    if (!queryInput.contains(e.target) && !suggestionsBox.contains(e.target)) {
        suggestionsBox.classList.add('hidden');
    }
});

// --- Initial setup when the page loads ---
toggleParams(); // Set the initial visibility of parameter sections based on the default model
weightValueSpan.textContent = hybridWeightSlider.value; // Set the initial text for the slider value

// --- Define all the functions for page interactivity ---

// Shows or hides the parameter sections based on the selected model
function toggleParams() {
    const selectedModel = modelSelect.value;
    // Show BM25 params if 'bm25' or 'hybrid' is selected, otherwise hide them
    bm25ParamsDiv.classList.toggle('hidden', !(selectedModel === 'bm25' || selectedModel === 'hybrid'));
    // Show hybrid params only if 'hybrid' is selected
    hybridParamsDiv.classList.toggle('hidden', selectedModel !== 'hybrid');
}

// Handles fetching suggestions as the user types
async function handleSuggestionInput() {
    clearTimeout(suggestionTimeout); // Clear any previous pending suggestion request
    const query = queryInput.value;

    // Don't fetch suggestions if the input is empty
    if (query.length < 1) {
        suggestionsBox.classList.add('hidden');
        return;
    }

    // Wait 250ms after the user stops typing before sending the request (debouncing)
    suggestionTimeout = setTimeout(async () => {
        const dataset = document.getElementById('dataset').value;
        try {
            const response = await fetch(`/suggest/?dataset_name=${encodeURIComponent(dataset)}&query=${encodeURIComponent(query)}`);
            const suggestions = await response.json();
            displaySuggestions(suggestions);
        } catch (error) {
            console.error("Suggestion fetch failed:", error);
        }
    }, 250);
}

// Displays the fetched suggestions in the suggestions box
function displaySuggestions(suggestions) {
    if (suggestions.length === 0) {
        suggestionsBox.classList.add('hidden');
        return;
    }
    suggestionsBox.innerHTML = ''; // Clear previous suggestions
    suggestions.forEach(suggestion => {
        const div = document.createElement('div');
        div.textContent = suggestion;
        div.className = 'p-2 hover:bg-gray-100 cursor-pointer';
        // When a suggestion is clicked, fill the input with it and hide the box
        div.onclick = () => {
            queryInput.value = suggestion;
            suggestionsBox.classList.add('hidden');
            queryInput.focus();
        };
        suggestionsBox.appendChild(div);
    });
    suggestionsBox.classList.remove('hidden'); // Show the box
}

// The main function to perform a search
async function performSearch() {
    // Gather all the data from the form into a single payload object
    const payload = {
        query: queryInput.value,
        dataset_name: document.getElementById('dataset').value,
        model_type: modelSelect.value,
        k1: parseFloat(document.getElementById('bm25_k1').value),
        b: parseFloat(document.getElementById('bm25_b').value),
        enable_ner_reranking: nerToggle.checked,
        enable_cluster_reranking: clusterToggle.checked,
        hybrid_bm25_weight: parseFloat(hybridWeightSlider.value),
        top_k: 10
    };

    // Don't search if the query is empty
    if (!payload.query.trim()) {
        statusDiv.innerHTML = `<p class="text-red-500 font-semibold">الرجاء إدخال استعلام للبحث.</p>`;
        return;
    }

    // Update the UI to show that a search is in progress
    statusDiv.innerHTML = '<div class="loader"></div><p class="text-blue-600 font-semibold">جاري البحث...</p>';
    resultsDiv.innerHTML = ''; // Clear old results
    alternativeSuggestionsDiv.innerHTML = ''; // Clear old suggestions
    searchBtn.disabled = true; // Disable the button to prevent multiple clicks

    // Fetch alternative suggestions (spelling, logs) in parallel with the main search
    fetchAlternativeSuggestions(payload.dataset_name, payload.query);

    try {
        // Send the payload to our Flask backend's /search endpoint
        const response = await fetch('/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const results = await response.json();
        // If the response was not OK, throw an error with the message from the backend
        if (!response.ok) throw new Error(results.error || 'حدث خطأ غير معروف.');
        
        statusDiv.innerHTML = ''; // Clear the status message
        displayResults(results); // Display the new results
    } catch (error) {
        // If an error occurred, show it in the status div
        statusDiv.innerHTML = `<p class="text-red-500 font-semibold">فشل البحث: ${error.message}</p>`;
    } finally {
        // Re-enable the search button, whether the search succeeded or failed
        searchBtn.disabled = false;
    }
}

// Renders the search results on the page
function displayResults(results) {
    if (!results || results.length === 0) {
        resultsDiv.innerHTML = '<p class="text-center text-gray-500">لم يتم العثور على نتائج.</p>';
        return;
    }
    // Loop through each result and create an HTML element for it
    results.forEach(result => {
        const resultEl = document.createElement('div');
        resultEl.className = 'bg-white p-5 rounded-xl shadow-md';
        const p = document.createElement('p');
        p.className = 'text-gray-700';
        p.textContent = result.original_text;
        // Use innerHTML to easily create the header with the doc ID and score
        resultEl.innerHTML = `
            <div class="flex justify-between items-center mb-2">
                <h3 class="text-lg font-bold text-gray-900">معرف المستند: ${result.doc_id}</h3>
                <div>
                    <p class="text-sm text-white bg-green-500 font-bold py-1 px-3 rounded-full inline-block">Cluster: ${result.cluster_id}</p>
                    <p class="text-sm text-white bg-blue-500 font-bold py-1 px-3 rounded-full inline-block ml-2">${result.score.toFixed(4)}</p>
                </div>
            </div>`;
        resultEl.appendChild(p); // Append the paragraph with the text
        resultsDiv.appendChild(resultEl); // Add the new result element to the page
    });
}

// Fetches and displays alternative suggestions
async function fetchAlternativeSuggestions(dataset, query) {
    try {
        const response = await fetch(`/suggest-alternatives/?dataset_name=${encodeURIComponent(dataset)}&query=${encodeURIComponent(query)}`);
        const suggestions = await response.json();
        displayAlternativeSuggestions(suggestions);
    } catch (error) {
        console.error("Alternative suggestion fetch failed:", error);
    }
}

// Displays the alternative suggestions (spelling correction, query logs)
function displayAlternativeSuggestions(suggestions) {
    alternativeSuggestionsDiv.innerHTML = ''; // Clear previous suggestions
    let content = '';

    // Display corrected query if available
    if (suggestions.corrected_query) {
        content += `<p class="mb-2">هل تقصد: <a href="#" class="text-blue-600 hover:underline" onclick="runNewSearch('${suggestions.corrected_query}')">${suggestions.corrected_query}</a></p>`;
    }

    // Display suggestions from query logs
    if (suggestions.log_suggestions && suggestions.log_suggestions.length > 0) {
        const logLinks = suggestions.log_suggestions.map(q => 
            `<a href="#" class="text-blue-600 hover:underline" onclick="runNewSearch('${q}')">${q}</a>`
        ).join(', ');
        content += `<p>استعلامات مشابهة: ${logLinks}</p>`;
    }

    if (content) {
        alternativeSuggestionsDiv.innerHTML = `<div class="bg-gray-100 p-4 rounded-lg">${content}</div>`;
    }
}

// Runs a new search with a suggested query
function runNewSearch(query) {
    queryInput.value = query;
    performSearch();
}
