// Keep duplicates and insertion order, including selections hidden by a new search.
function add(selected, glyph) {
    return glyph ? selected.concat([glyph]) : selected;
}

function removeAt(selected, index) {
    return selected.filter((value, position) => position !== index);
}

function removeLast(selected, glyph) {
    return removeAt(selected, selected.lastIndexOf(glyph));
}

function values(selected, entry) {
    return selected.length ? selected : entry && entry.emoji ? [entry.emoji] : [];
}
