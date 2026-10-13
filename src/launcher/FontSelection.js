// Keep selections independent of the current search results.
function key(entry) {
    return entry.selectionKey || entry.target || entry.repository + "/" + entry.name;
}

function eligible(entry) {
    return entry && (entry.target || (entry.repository && !entry.installed));
}

function contains(selection, entry) {
    return selection.some(item => key(item) === key(entry));
}

function toggle(selection, entry) {
    if (!eligible(entry))
        return selection;
    return contains(selection, entry)
        ? selection.filter(item => key(item) !== key(entry))
        : selection.concat([entry]);
}

function targets(selection, highlighted) {
    return selection.length ? selection : eligible(highlighted) ? [highlighted] : [];
}

function argumentsFor(entries, removing) {
    if (removing) {
        const paths = entries.reduce((args, entry) => args.concat(entry.targets || [entry.target]), []);
        return paths.filter((path, index) => paths.indexOf(path) === index);
    }
    return entries.reduce((args, entry) => args.concat([entry.name, entry.repository]), []);
}
