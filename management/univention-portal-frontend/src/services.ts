import {CategoryData, EntryData, PortalData} from '@/types';

const services =  {
    getPortal: () => {
        return new Promise<PortalData>((resolve, reject) => {
            setTimeout(() => {
                resolve({
                    title_localized: 'DEMOPORTAL',
                    content: [
                        ['category_1', ['entry_1', 'entry_2']],
                        ['category_2', ['entry_3', 'entry_1']],
                    ],
                });
            }, 750);
        });
    },
    getCategories: () => {
        return new Promise<CategoryData>((resolve, reject) => {
            setTimeout(() => {
                let data: CategoryData;
                data = {
                    category_1: {title_localized: 'Category 1'},
                    category_2: {title_localized: 'Category 2'},
                };
                resolve(data);
            }, 1000);
        });
    },
    getEntries: () => {
        return new Promise<EntryData>((resolve, reject) => {
            setTimeout(() => {
                resolve({
                    entry_1: {title_localized: 'Entry 1'},
                    entry_2: {title_localized: 'Entry 2'},
                    entry_3: {title_localized: 'Entry 3'},
                });
            }, 750);
        });
    },
};

export default services;
