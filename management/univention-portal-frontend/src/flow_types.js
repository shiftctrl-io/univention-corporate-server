// @flow

export type Dn = string;

export type LangDict = {
    [lang_code: string]: string
}

export type CategoryDatum = {
    dn: Dn,
    display_name: LangDict,
    display_name_localized: string
}

export type EntryDatum = {
    dn: Dn,
    name: LangDict,
    name_localized?: string,
    description: LangDict,
    description_localized?: string,
    logo_name: string,
    allowedGroups?: Dn[]
}

export type PortalDataRaw = {
    title: LangDict,
    title_localized?: string,
    content: Array<[Dn, Array<Dn>]>
};

export type CategoryDataRaw = {
    [c_dn: Dn]: CategoryDatum
};

export type EntryDataRaw = {
    [e_dn: Dn]: EntryDatum
};
