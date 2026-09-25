import { useId, useRef, type KeyboardEvent } from 'react';
import { motion } from 'motion/react';
import { GLIDE } from '../../utils/motion';

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string> {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: 'sm' | 'md';
  mono?: boolean;
}

/** Compact tab switcher with a gliding surface pill. Arrow keys move between tabs. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  size = 'md',
  mono = false,
}: SegmentedControlProps<T>) {
  const id = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = options.findIndex((o) => o.value === value);
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % options.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + options.length) % options.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = options.length - 1;
    else return;
    event.preventDefault();
    event.stopPropagation();
    onChange(options[next].value);
    refs.current[next]?.focus();
  };

  const pad = size === 'sm' ? 'px-2.5 py-1 text-[12px]' : 'px-3 py-1.5 text-[13px]';

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className="inline-flex items-center gap-0.5 rounded-lg border border-line bg-mist/70 p-0.5"
    >
      {options.map((option, i) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(option.value)}
            className={`relative rounded-md font-medium whitespace-nowrap transition-colors duration-150 ${pad} ${mono ? 'data' : ''} ${
              active ? 'text-ink' : 'text-muted hover:text-ink'
            }`}
          >
            {active && (
              <motion.span
                layoutId={`${id}-pill`}
                className="absolute inset-0 rounded-md bg-surface shadow-[0_1px_2px_rgb(20_32_43/0.08),0_0_0_1px_rgb(20_32_43/0.04)]"
                transition={GLIDE}
              />
            )}
            <span className="relative">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
