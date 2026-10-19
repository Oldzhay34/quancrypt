import { useQuery } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useApi } from '../api/ApiProvider';
import type { Project } from '../api/types';
import { listProjects } from './api';

const STORAGE_KEY = 'quancrypt.project';

function savedProjectId(): string | null {
    try {
        return window.sessionStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
}

export type ProjectStatus = 'loading' | 'error' | 'empty' | 'ready';

interface ProjectValue {
    status: ProjectStatus;
    projects: Project[];
    /** The selected project: the only one, or the saved choice, or the newest (the list is newest first). */
    project: Project | null;
    selectProject: (id: string) => void;
    retry: () => void;
}

const ProjectContext = createContext<ProjectValue | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
    const api = useApi();
    const [chosen, setChosen] = useState<string | null>(savedProjectId);
    const query = useQuery({ queryKey: ['projects'], queryFn: ({ signal }) => listProjects(api, signal) });

    const selectProject = useCallback((id: string) => {
        setChosen(id);
        try {
            window.sessionStorage.setItem(STORAGE_KEY, id);
        } catch {
            // The choice then lasts for this page only.
        }
    }, []);

    const value = useMemo<ProjectValue>(() => {
        const projects = query.data ?? [];
        const project = projects.find((item) => item.id === chosen) ?? projects[0] ?? null;
        const status: ProjectStatus = query.isPending
            ? 'loading'
            : query.isError
              ? 'error'
              : projects.length === 0
                ? 'empty'
                : 'ready';
        return { status, projects, project, selectProject, retry: () => void query.refetch() };
    }, [query, chosen, selectProject]);

    return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject(): ProjectValue {
    const value = useContext(ProjectContext);
    if (!value) throw new Error('useProject must be used inside ProjectProvider');
    return value;
}
