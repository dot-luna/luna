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
