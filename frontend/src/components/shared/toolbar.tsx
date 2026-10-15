// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-15
// Scope: Added the reusable configurable toolbar used by supplier and errand pages.
// Author review: <to be completed by author>

import type { MouseEventHandler } from 'react'
import { DropdownMenu } from 'radix-ui'
import {
  ArrowUpDown,
  Check,
  ChevronDown,
  Filter as FilterIcon,
  Plus,
  Search,
} from 'lucide-react'
import type { ToolbarOption } from '../../types/toolbar'
import './toolbar.css'

type ChoiceConfig = {
  options: ToolbarOption[]
  value: string
  onChange: (value: string) => void
  label: string
}

type SearchConfig = {
  value: string
  onChange: (value: string) => void
  placeholder: string
  label: string
  maxLength?: number
}

type CreateAction = {
  label: string
  onClick: MouseEventHandler<HTMLButtonElement>
}

type LeadingContent =
  | { tabs: ChoiceConfig; subheader?: never }
  | { tabs?: never; subheader: string }

type Props = LeadingContent & {
  search?: SearchConfig
  sort: ChoiceConfig
  filter?: ChoiceConfig
  createAction?: CreateAction
}

function ChoiceMenu({
  config,
  kind,
}: {
  config: ChoiceConfig
  kind: 'filter' | 'sort'
}) {
  const selected =
    config.options.find((option) => option.value === config.value)?.label ??
    config.value
  const Icon = kind === 'filter' ? FilterIcon : ArrowUpDown

  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button
          className="toolbar-choice"
          type="button"
          aria-label={`${config.label}: ${selected}`}
        >
          <Icon size={16} aria-hidden="true" />
          <span>{selected}</span>
          <ChevronDown size={15} aria-hidden="true" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="toolbar-menu"
          align="end"
          sideOffset={6}
          collisionPadding={12}
        >
          <DropdownMenu.RadioGroup
            value={config.value}
            onValueChange={config.onChange}
            aria-label={config.label}
          >
            {config.options.map((option) => (
              <DropdownMenu.RadioItem
                className="toolbar-option"
                key={option.value}
                value={option.value}
              >
                {option.label}
                <DropdownMenu.ItemIndicator>
                  <Check size={16} aria-hidden="true" />
                </DropdownMenu.ItemIndicator>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

export default function Toolbar({
  tabs,
  subheader,
  search,
  sort,
  filter,
  createAction,
}: Props) {
  return (
    <section
      className="toolbar"
      aria-label={subheader ?? tabs?.label ?? search?.label}
    >
      {tabs ? (
        <div className="toolbar-tabs" role="tablist" aria-label={tabs.label}>
          {tabs.options.map((tab) => (
            <button
              className={tabs.value === tab.value ? 'is-active' : ''}
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={tabs.value === tab.value}
              onClick={() => tabs.onChange(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : (
        <h4 className="toolbar-subheader">{subheader}</h4>
      )}

      <div className="toolbar-controls">
        {search && (
          <label className="toolbar-search">
            <Search size={18} aria-hidden="true" />
            <input
              value={search.value}
              onChange={(event) => search.onChange(event.target.value)}
              placeholder={search.placeholder}
              aria-label={search.label}
              maxLength={search.maxLength}
            />
          </label>
        )}
        {filter && <ChoiceMenu config={filter} kind="filter" />}

        <ChoiceMenu config={sort} kind="sort" />
        {createAction && (
          <button
            className="toolbar-create"
            type="button"
            aria-label={createAction.label}
            onClick={createAction.onClick}
          >
            <Plus size={18} aria-hidden="true" />
          </button>
        )}
      </div>
    </section>
  )
}
