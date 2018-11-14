export type ContentEntry = [CategoryType, EntryType[]];

export interface CategoryType {
    title: string;
}

export interface EntryType {
    title: string;
}

export interface PortalType {
    title: string;
    content: Array<ContentEntry>;
}

export interface PortalData {
    title_localized: string;
    content: Array<[string, string[]]>;
}

export interface EntryData {
    [key: string]: EntryDatum;
}

export interface EntryDatum {
    title_localized: string;
}

export interface CategoryData {
    [key: string]: CategoryDatum;
}

export interface CategoryDatum {
    title_localized: string;
}
