export type AgentRecord = {
    agent_id: number;
    agent_type: string;
    kwargs: Record<string, any>;
};

export type AgentClassInfo = {
    type: string;
    class_name: string;
    description?: string;
    is_custom?: boolean;
};

export type AgentFormValues = {
    agent_id: number;
    agent_type: string;
    name: string;
    profile_json: string;
    kwargs_json: string;
};

export const jsonStringify = (value: any) => JSON.stringify(value ?? {}, null, 2);

export const parseJsonObject = (value: string, label: string) => {
    try {
        const parsed = JSON.parse(value || '{}');
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
            throw new Error(`${label} must be a JSON object`);
        }
        return parsed;
    } catch (error) {
        throw new Error(`${label}: ${error instanceof Error ? error.message : String(error)}`);
    }
};

export const buildAgentFromForm = (values: AgentFormValues): AgentRecord => {
    const profile = parseJsonObject(values.profile_json, 'profile_json');
    const extraKwargs = parseJsonObject(values.kwargs_json, 'kwargs_json');
    profile.name = profile.name || values.name;
    return {
        agent_id: Number(values.agent_id),
        agent_type: values.agent_type,
        kwargs: {
            ...extraKwargs,
            id: Number(values.agent_id),
            name: values.name,
            profile,
        },
    };
};
