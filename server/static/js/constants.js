// Display constants shared by more than one panel.
//
// They live in a module of their own because the panels that use them import
// each other, and a `const` exported across an import cycle is not guaranteed
// to be initialised by the time the other side evaluates.

export const COMMODITY_TYPES = ['cloth', 'coin', 'paper'];
