// Navigation owns blank plot space; Contigs and controls retain their own actions.
export const VIEW_CONTIG_TARGET = "[data-track-contig-id][data-track-role], [data-subview-contig-id][data-subview-track-slot], [data-subview-track-pair-contig-id], [data-subview-fragment-key]";
export const VIEW_CONTROL_TARGET = 'button,input,select,textarea,a[href],summary,[contenteditable]:not([contenteditable="false"])';
export const isViewBoxSelectionEvent = event => Boolean(event.ctrlKey || event.metaKey) && !event.altKey;
