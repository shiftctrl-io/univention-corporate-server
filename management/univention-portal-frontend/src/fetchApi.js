// @flow

/**
 * This module mocks API calls to a remote data resource and returns the data in the form expected from the server.
 */

/*::
import type {PortalDataRaw, CategoryDataRaw, EntryDataRaw} from "./flow_types";
*/

export const fetchPortal = function () {
    return new Promise/*::<PortalDataRaw>*/((resolve) => {
        setTimeout(() => {
            const data = {
                title: {
                    de_DE: 'Demo portal DE',
                    en_US: 'Demo portal EN'
                },
                title_localized: 'Demo portal',
                content: [
                    ['category_1', ['entry_1', 'entry_2']],
                    ['category_2', ['entry_3', 'entry_1']],
                ],
            };
            resolve(data)
        }, 1250)
    })
};

export const fetchCategories = function () {
    return new Promise/*::<CategoryDataRaw>*/((resolve) => {
        setTimeout(() => {
            const data = {
                category_1: {dn: 'category_1', display_name_localized: 'Category 1', display_name: {}},
                category_2: {dn: 'category_2', display_name_localized: 'Category 2', display_name: {}},
            };
            resolve(data)
        }, 750)
    });
};

export const fetchEntries = function () {
    return new Promise/*::<EntryDataRaw>*/((resolve) => {
        setTimeout(() => {
            const data = {
                entry_1: {
                    dn: 'entry_1',
                    name_localized: 'Entry 1',
                    name: {},
                    description_localized: '',
                    description: {},
                    logo_name: ''
                },
                entry_2: {
                    dn: 'entry_2',
                    name_localized: 'Entry 2',
                    name: {},
                    description_localized: '',
                    description: {},
                    logo_name: ''
                },
                entry_3: {
                    dn: 'entry_3',
                    name_localized: 'Entry 3',
                    name: {},
                    description_localized: '',
                    description: {},
                    logo_name: ''
                },
            };
            resolve(data)
        }, 1300)
    });
};
