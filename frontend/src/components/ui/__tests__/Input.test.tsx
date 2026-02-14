/**
 * Input Component Tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, userEvent } from '@/test/utils';
import { Input } from '../input';

describe('Input', () => {
  it('renders with default type text', () => {
    render(<Input placeholder="Enter text" />);
    const input = screen.getByPlaceholderText(/enter text/i);

    expect(input).toBeInTheDocument();
    // Input component doesn't set type="text" by default (browser default)
    const inputElement = input as HTMLInputElement;
    expect(inputElement.type).toBe('text'); // Browser default type
  });

  it('renders with different types', () => {
    const { rerender } = render(<Input type="email" placeholder="Email" />);
    expect(screen.getByPlaceholderText(/email/i)).toHaveAttribute('type', 'email');

    rerender(<Input type="password" placeholder="Password" />);
    expect(screen.getByPlaceholderText(/password/i)).toHaveAttribute('type', 'password');

    rerender(<Input type="number" placeholder="Number" />);
    expect(screen.getByPlaceholderText(/number/i)).toHaveAttribute('type', 'number');
  });

  it('handles user input', async () => {
    const user = userEvent.setup();
    render(<Input placeholder="Type here" />);
    const input = screen.getByPlaceholderText(/type here/i) as HTMLInputElement;

    await user.type(input, 'Test input');
    expect(input.value).toBe('Test input');
  });

  it('calls onChange handler', async () => {
    const handleChange = vi.fn();
    const user = userEvent.setup();

    render(<Input onChange={handleChange} placeholder="Input" />);
    const input = screen.getByPlaceholderText(/input/i);

    await user.type(input, 'a');
    expect(handleChange).toHaveBeenCalled();
  });

  it('can be disabled', async () => {
    const user = userEvent.setup();
    render(<Input disabled placeholder="Disabled input" />);
    const input = screen.getByPlaceholderText(/disabled input/i) as HTMLInputElement;

    expect(input).toBeDisabled();
    expect(input).toHaveClass('disabled:opacity-50');

    await user.type(input, 'test');
    expect(input.value).toBe(''); // Sollte leer bleiben
  });

  it('supports German umlauts', async () => {
    const user = userEvent.setup();
    render(<Input placeholder="Eingabe" />);
    const input = screen.getByPlaceholderText(/eingabe/i) as HTMLInputElement;

    await user.type(input, 'Müller');
    expect(input.value).toBe('Müller');

    await user.clear(input);
    await user.type(input, 'Größe');
    expect(input.value).toBe('Größe');
  });

  it('accepts custom className', () => {
    render(<Input className="custom-input" placeholder="Custom" />);
    const input = screen.getByPlaceholderText(/custom/i);

    expect(input).toHaveClass('custom-input');
    expect(input).toHaveClass('rounded-md'); // default class
  });

  it('supports focus states', async () => {
    const user = userEvent.setup();
    render(<Input placeholder="Focus test" />);
    const input = screen.getByPlaceholderText(/focus test/i);

    await user.click(input);
    expect(input).toHaveFocus();
    expect(input).toHaveClass('focus-visible:ring-1');
  });

  it('renders with value prop (controlled)', () => {
    const { rerender } = render(<Input value="Initial" onChange={() => {}} />);
    const input = screen.getByDisplayValue('Initial') as HTMLInputElement;

    expect(input.value).toBe('Initial');

    rerender(<Input value="Updated" onChange={() => {}} />);
    expect(input.value).toBe('Updated');
  });
});
