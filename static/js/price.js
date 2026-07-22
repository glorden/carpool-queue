function normalize(text) {
    return text.toLowerCase().replace(/ё/g, "е").trim();
}

function initPriceSearch() {
    const input = document.getElementById("price-search");
    const noResults = document.getElementById("price-no-results");
    if (!input) return;

    const items = Array.from(document.querySelectorAll(".price-list li"));
    const groups = Array.from(document.querySelectorAll(".price-list"));
    const sections = Array.from(document.querySelectorAll(".price-section"));

    input.addEventListener("input", () => {
        const query = normalize(input.value);

        items.forEach((li) => {
            const name = normalize(li.querySelector("span").textContent);
            li.style.display = query === "" || name.includes(query) ? "" : "none";
        });

        groups.forEach((ul) => {
            const hasVisibleItem = Array.from(ul.children).some(
                (li) => li.style.display !== "none"
            );
            ul.style.display = hasVisibleItem ? "" : "none";
        });

        sections.forEach((section) => {
            const hasVisibleGroup = Array.from(
                section.querySelectorAll(".price-list")
            ).some((ul) => ul.style.display !== "none");
            section.style.display = hasVisibleGroup ? "" : "none";
        });

        if (noResults) {
            const anyVisible = sections.some((s) => s.style.display !== "none");
            noResults.style.display = anyVisible ? "none" : "";
        }
    });
}

initPriceSearch();
