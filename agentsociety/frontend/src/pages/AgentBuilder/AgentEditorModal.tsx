import React from 'react';
import {
    Col,
    Form,
    Input,
    InputNumber,
    Modal,
    Row,
    Select,
    message,
} from 'antd';
import type { FormInstance } from 'antd/es/form';
import {
    buildAgentFromForm,
    type AgentClassInfo,
    type AgentFormValues,
    type AgentRecord,
} from './agentEditor';

type AgentEditorModalProps = {
    open: boolean;
    editingAgentId: number | null;
    form: FormInstance<AgentFormValues>;
    agentClasses?: AgentClassInfo[];
    width?: number;
    minAgentId?: number;
    onCancel: () => void;
    onSave: (agent: AgentRecord) => void | Promise<void>;
};

export const AgentEditorModal: React.FC<AgentEditorModalProps> = ({
    open,
    editingAgentId,
    form,
    agentClasses = [],
    width = 760,
    minAgentId = 0,
    onCancel,
    onSave,
}) => {
    const submitAgent = async () => {
        try {
            const values = await form.validateFields();
            await onSave(buildAgentFromForm(values));
        } catch (error) {
            message.error(error instanceof Error ? error.message : 'Agent form is invalid.');
        }
    };

    return (
        <Modal
            title={editingAgentId === null ? 'Add Agent' : 'Edit Agent'}
            open={open}
            onOk={submitAgent}
            onCancel={onCancel}
            width={width}
            destroyOnHidden
            forceRender
        >
            <Form form={form} layout="vertical">
                <Row gutter={12}>
                    <Col span={8}>
                        <Form.Item name="agent_id" label="Agent ID" rules={[{ required: true }]}>
                            <InputNumber min={minAgentId} style={{ width: '100%' }} />
                        </Form.Item>
                    </Col>
                    <Col span={8}>
                        <Form.Item name="agent_type" label="Agent Type" rules={[{ required: true }]}>
                            {agentClasses.length ? (
                                <Select
                                    showSearch
                                    options={agentClasses.map((item) => ({
                                        value: item.type,
                                        label: `${item.type}${item.is_custom ? ' (custom)' : ''}`,
                                    }))}
                                />
                            ) : (
                                <Input />
                            )}
                        </Form.Item>
                    </Col>
                    <Col span={8}>
                        <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                            <Input />
                        </Form.Item>
                    </Col>
                </Row>
                <Form.Item name="profile_json" label="Profile JSON" rules={[{ required: true }]}>
                    <Input.TextArea rows={8} spellCheck={false} />
                </Form.Item>
                <Form.Item name="kwargs_json" label="Extra kwargs JSON">
                    <Input.TextArea rows={6} spellCheck={false} />
                </Form.Item>
            </Form>
        </Modal>
    );
};
