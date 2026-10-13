// Rank name matches first, then match words against the entry's searchable metadata.
function find(entries, query) {
    const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    return entries.filter(entry => {
        if (entry.noDisplay || !entry.command || !entry.command.length)
            return false;
        const fields = [entry.name, entry.genericName, entry.comment, entry.id]
            .concat(entry.keywords || []).join(" ").toLocaleLowerCase();
        return words.every(word => fields.includes(word));
    }).sort((a, b) => {
        const nameA = a.name.toLocaleLowerCase();
        const nameB = b.name.toLocaleLowerCase();
        const score = name => words.reduce((sum, word) => sum + (name.startsWith(word) ? 0 : name.includes(word) ? 1 : 2), 0);
        return score(nameA) - score(nameB) || nameA.localeCompare(nameB) || a.id.localeCompare(b.id);
    });
}

// Empty queries show immediate children; searches include descendants of this menu.
function rootEntries(menuEntries, applications, query, route) {
    route = route || "";
    const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    const sections = menuEntries.filter(entry => {
        const parent = entry.parent || "";
        if (!words.length)
            return parent === route;
        if (route && parent !== route && !parent.startsWith(route + "."))
            return false;
        const text = [entry.name, entry.parentLabel || ""].join(" ").toLocaleLowerCase();
        return words.every(word => text.includes(word));
    });
    return !route && words.length ? sections.concat(find(applications, query)) : sections;
}

// Installed entries are removal units: packages or exact user font files.
function installedFonts(entries, query) {
    const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    return entries.filter(entry => {
        const text = [entry.name, entry.description, entry.repository].join(" ").toLocaleLowerCase();
        return words.every(word => text.includes(word));
    });
}
